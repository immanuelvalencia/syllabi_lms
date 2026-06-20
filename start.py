import os
import sys
import subprocess

def main():
    print('Running migrations...')
    subprocess.run([sys.executable, 'manage.py', 'migrate'], check=True)
    print('Initializing admin...')
    subprocess.run([sys.executable, 'manage.py', 'initadmin'])
    
    port = os.environ.get('PORT', '8000')
    print(f'Starting gunicorn on port {port}...')
    os.execvp('gunicorn', ['gunicorn', 'config.wsgi:application', '--bind', f'0.0.0.0:{port}', '--workers', '3', '--threads', '2'])

if __name__ == '__main__':
    main()
