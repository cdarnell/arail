from arail.lab_brain import build_chat_messages

msgs = build_chat_messages('What is the default MLX model?', [])
for m in msgs:
    if m['role'] == 'system':
        found = 'Retrieved knowledge base context' in m['content']
        print(f"System message contains context: {found}")
        # print(m['content']) # Uncomment for debug
