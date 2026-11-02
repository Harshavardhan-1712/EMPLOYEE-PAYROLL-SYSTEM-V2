import json
import urllib.request
import urllib.error
from getpass import getpass

username = input("Username [admin]: ").strip() or "admin"
password = getpass("Enter password: ")

data = json.dumps({
    "username": username,
    "password": password
}).encode("utf-8")

request = urllib.request.Request(
    "http://127.0.0.1:8000/api/auth/login",
    data=data,
    headers={"Content-Type": "application/json"},
    method="POST",
)

try:
    with urllib.request.urlopen(request) as response:
        print("STATUS:", response.status)
        print("RESPONSE:", response.read().decode())
except urllib.error.HTTPError as error:
    print("STATUS:", error.code)
    print("RESPONSE:", error.read().decode())
except Exception as error:
    print("CONNECTION ERROR:", str(error))