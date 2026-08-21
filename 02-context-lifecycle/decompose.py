#!/usr/bin/env python3
"""
Decompose raw HTTP capture files into a structured CSV with session detection.

For each .raw file (concatenated HTTP requests from a logging proxy), extract
every JSON object containing a "messages" key by walking the bytes and
brace-matching all candidates, skipping anything unparseable.

Output CSV columns:
  file, req_idx, session_id, event, model, n_messages, total_chars,
  system_chars, user_chars, assistant_chars, tool_chars, toolschema_chars,
  delta_chars_vs_prev

Event classification:
  - "append":       the previous conversation state's message list is a prefix
                    of the current one (the last assistant message is allowed
                    to differ, as it gets appended to)
  - "new_session":  no prefix relationship with the previous state
  - "compaction":   model and system prompt match the previous state, the
                    message list is shorter/rewritten, and total size dropped
                    by more than 30%
  - "aux_request":  an auxiliary call from the client (e.g. pi's compaction
                    summarisation request: the whole history stuffed into one
                    user message). Detected as: no tools array, at most 3
                    messages, user content dominating (>90% of the request)
                    and large in absolute terms (>20,000 chars). These are
                    NOT conversation states: they are excluded from the state
                    chain, so compaction deltas are computed against the last
                    true conversation state, not against the summarisation
                    payload.

Session IDs are globally unique across input files (a single counter that
never resets), so grouping by session_id alone is safe downstream. Sessions
never continue across files; if a session spans a midnight log rotation it
will be counted twice, which is accepted and noted here.
"""

import csv
import json
import os
import sys


def find_json_objects_with_messages(data: bytes):
    """
    Walk through raw bytes and return every brace-matched candidate that
    parses as JSON and contains a 'messages' key, in file order.
    """
    results = []
    depth = 0
    start = None
    i = 0
    n = len(data)

    while i < n:
        ch = data[i:i + 1]
        if ch == b'"':
            # Skip the string literal, handling escapes
            j = i + 1
            while j < n:
                c2 = data[j:j + 1]
                if c2 == b'\\':
                    j += 2
                    continue
                if c2 == b'"':
                    break
                j += 1
            i = j + 1
            continue
        if ch == b'{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == b'}':
            depth -= 1
            if depth == 0 and start is not None:
                candidate = data[start:i + 1]
                try:
                    obj = json.loads(candidate.decode('utf-8', errors='replace'))
                    if isinstance(obj, dict) and 'messages' in obj:
                        results.append(obj)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
                start = None
        i += 1

    return results


def count_content_chars(msg):
    """Character length of a message's content, handling string or list forms."""
    content = msg.get('content')
    if content is None:
        return 0
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        total = 0
        for part in content:
            if isinstance(part, dict):
                text = part.get('text', '')
                if isinstance(text, str):
                    total += len(text)
                elif isinstance(text, list):
                    for sub in text:
                        if isinstance(sub, str):
                            total += len(sub)
            # image_url, audio_url and similar are ignored
        return total
    return 0


def count_tool_calls_chars(msg):
    """Characters contributed by tool_calls on assistant messages."""
    tc = msg.get('tool_calls')
    if not tc:
        return 0
    total = 0
    for call in tc:
        total += len(json.dumps(call))
    return total


def extract_metrics(obj):
    """Extract all metrics from a parsed JSON request object."""
    messages = obj.get('messages', [])
    model = obj.get('model', '')

    system_chars = 0
    user_chars = 0
    assistant_chars = 0
    tool_chars = 0

    for msg in messages:
        role = msg.get('role', '')
        cc = count_content_chars(msg)
        if role == 'system':
            system_chars += cc
        elif role == 'user':
            user_chars += cc
        elif role == 'assistant':
            assistant_chars += cc
            assistant_chars += count_tool_calls_chars(msg)
        elif role == 'tool':
            tool_chars += cc

    toolschema_chars = 0
    tools = obj.get('tools')
    if tools:
        toolschema_chars = len(json.dumps(tools))

    total_chars = (system_chars + user_chars + assistant_chars
                   + tool_chars + toolschema_chars)

    return {
        'model': model,
        'n_messages': len(messages),
        'total_chars': total_chars,
        'system_chars': system_chars,
        'user_chars': user_chars,
        'assistant_chars': assistant_chars,
        'tool_chars': tool_chars,
        'toolschema_chars': toolschema_chars,
        'messages': messages,  # kept for session detection
    }


def is_aux_request(metrics):
    """
    Detect auxiliary client calls (summarisation requests and similar):
    no tools array, at most 3 messages, user content dominating and large.
    Conversation states in this corpus always carry a tools array, and no
    human types 20,000 characters into a chat box.
    """
    if metrics['toolschema_chars'] != 0:
        return False
    if metrics['n_messages'] > 3:
        return False
    if metrics['total_chars'] == 0:
        return False
    if metrics['user_chars'] / metrics['total_chars'] <= 0.90:
        return False
    if metrics['user_chars'] <= 20000:
        return False
    return True


def messages_are_prefix(prev_msgs, curr_msgs):
    """
    True if prev_msgs is a prefix of curr_msgs. The last assistant message
    is allowed to differ in content (it gets appended to between requests).
    """
    if len(prev_msgs) == 0:
        return True
    if len(curr_msgs) < len(prev_msgs):
        return False

    for i in range(len(prev_msgs) - 1):
        if i >= len(curr_msgs):
            return False
        if (json.dumps(prev_msgs[i], sort_keys=True)
                != json.dumps(curr_msgs[i], sort_keys=True)):
            return False

    prev_last = prev_msgs[-1]
    curr_last = curr_msgs[len(prev_msgs) - 1]

    if prev_last.get('role') == 'assistant':
        pm_copy = dict(prev_last)
        cm_copy = dict(curr_last)
        for k in ('content', 'tool_calls'):
            pm_copy.pop(k, None)
            cm_copy.pop(k, None)
        return (json.dumps(pm_copy, sort_keys=True)
                == json.dumps(cm_copy, sort_keys=True))

    return (json.dumps(prev_last, sort_keys=True)
            == json.dumps(curr_last, sort_keys=True))


def is_compaction(prev_metrics, curr_metrics):
    """
    Compaction: same model, identical system prompt, message list rewritten,
    and total size dropped by more than 30% against the previous true
    conversation state.
    """
    if prev_metrics is None:
        return False

    if prev_metrics['model'] != curr_metrics['model']:
        return False

    if prev_metrics['system_chars'] != curr_metrics['system_chars']:
        return False

    prev_sys = [m for m in prev_metrics['messages'] if m.get('role') == 'system']
    curr_sys = [m for m in curr_metrics['messages'] if m.get('role') == 'system']
    if json.dumps(prev_sys, sort_keys=True) != json.dumps(curr_sys, sort_keys=True):
        return False

    if curr_metrics['total_chars'] == 0:
        return False

    drop_ratio = ((prev_metrics['total_chars'] - curr_metrics['total_chars'])
                  / prev_metrics['total_chars'])
    return drop_ratio > 0.30


def classify_event(prev_state, curr_metrics):
    """
    Classify the current request. prev_state is the last true conversation
    state (aux requests never become prev_state).
    """
    if is_aux_request(curr_metrics):
        return 'aux_request'

    if prev_state is None:
        return 'new_session'

    if messages_are_prefix(prev_state['messages'], curr_metrics['messages']):
        return 'append'

    if is_compaction(prev_state, curr_metrics):
        return 'compaction'

    return 'new_session'


def process_file(filepath, session_counter):
    """
    Process a single raw file. session_counter is a one-element list holding
    the global session counter, so numbering never resets across files.
    Returns the list of record dicts.
    """
    basename = os.path.basename(filepath)
    data = open(filepath, 'rb').read()
    objects = find_json_objects_with_messages(data)

    records = []
    prev_state = None       # last true conversation state
    current_session = None  # session id of the state chain

    for req_idx, obj in enumerate(objects):
        metrics = extract_metrics(obj)
        event = classify_event(prev_state, metrics)

        if event == 'new_session':
            session_counter[0] += 1
            current_session = session_counter[0]

        # Aux requests belong to the surrounding session but do not have one
        # of their own; if a file opens with an aux request, park it in a
        # fresh session so the column is never empty.
        if current_session is None:
            session_counter[0] += 1
            current_session = session_counter[0]

        if event == 'aux_request':
            delta = 0
        else:
            delta = (metrics['total_chars'] - prev_state['total_chars']
                     if prev_state else 0)

        records.append({
            'file': basename,
            'req_idx': req_idx,
            'session_id': current_session,
            'event': event,
            'model': metrics['model'],
            'n_messages': metrics['n_messages'],
            'total_chars': metrics['total_chars'],
            'system_chars': metrics['system_chars'],
            'user_chars': metrics['user_chars'],
            'assistant_chars': metrics['assistant_chars'],
            'tool_chars': metrics['tool_chars'],
            'toolschema_chars': metrics['toolschema_chars'],
            'delta_chars_vs_prev': delta,
        })

        # Only true conversation states advance the chain
        if event != 'aux_request':
            prev_state = metrics

    return records


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <output.csv> <file1.raw> [file2.raw ...]",
              file=sys.stderr)
        sys.exit(1)

    output_csv = sys.argv[1]

    all_records = []
    session_counter = [0]
    for filepath in sys.argv[2:]:
        if not os.path.isfile(filepath):
            print(f"Warning: {filepath} not found, skipping", file=sys.stderr)
            continue
        all_records.extend(process_file(filepath, session_counter))

    fieldnames = [
        'file', 'req_idx', 'session_id', 'event', 'model',
        'n_messages', 'total_chars', 'system_chars', 'user_chars',
        'assistant_chars', 'tool_chars', 'toolschema_chars',
        'delta_chars_vs_prev',
    ]

    with open(output_csv, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rec in all_records:
            writer.writerow(rec)

    n_aux = sum(1 for r in all_records if r['event'] == 'aux_request')
    print(f"Wrote {len(all_records)} rows to {output_csv} "
          f"({session_counter[0]} sessions, {n_aux} aux requests)",
          file=sys.stderr)


if __name__ == '__main__':
    main()

