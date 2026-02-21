from app import create_app, socketio
import os
import sys

# defaults
PORT = os.environ.get('PORT', 80)
HOST = '0.0.0.0'
DEBUG = os.environ.get('DEBUG', 'false').lower() in ('true', '1', 'yes')

if len(sys.argv) != 1 and len(sys.argv) != 3:
    print("Usage: python {} OR python {} <HostName> <PortNumber>".format(sys.argv[0], sys.argv[0]))
    sys.exit()

if len(sys.argv) == 3:
    HOST = sys.argv[1]
    PORT = int(sys.argv[2])

app = create_app(debug=DEBUG)

if __name__ == '__main__':
    socketio.run(app, host=HOST, port=PORT, use_reloader=False)
