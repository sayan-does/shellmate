from config.secrets import redact_secrets

prompt = 'API key is sk-1234567890abcdef and token is ghp_1234567890abcdef'
result = redact_secrets(prompt)
print('Input:', prompt)
print('Output:', result)
print('ghp_ in result:', 'ghp_1234567890abcdef' in result)

text = "curl -H 'Authorization: Bearer token123' example.com"
result2 = redact_secrets(text)
print('Bearer Input:', text)
print('Bearer Output:', result2)