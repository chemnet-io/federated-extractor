import os
from ollama import Client

client = Client(
    host='http://141.57.8.18:11434',
    headers={'Authorization': 'Bearer ' + os.environ.get('OLLAMA_API_KEY')}
)

messages = [
  {
    'role': 'user',
    'content': 'What is RDF?',
  },
]

for part in client.chat('gemma4:e4b', messages=messages, stream=True):
  print(part.message.content, end='', flush=True)