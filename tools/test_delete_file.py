import os, tempfile
import sys
sys.path.insert(0, '.')
from app import create_app
app = create_app()
# create temp file
fd, path = tempfile.mkstemp(prefix='test_delete_', dir='.')
os.close(fd)
print('Created', path)
with app.test_client() as c:
    resp = c.post('/delete_file', json={'filename': path, 'type': 'brew'})
    print('Status:', resp.status_code, 'JSON:', resp.get_json())
print('Exists after:', os.path.exists(path))
