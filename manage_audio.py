#! /opt/anaconda3/bin/python

import socket
import subprocess
import sys
import signal
from datetime import datetime, timedelta
import threading

# Configuration
HOST = '0.0.0.0'  # Listen on all interfaces
PORT = 2973       # Port to listen on
COOLDOWN_SECONDS = 5  # Minimum time (in seconds) between processing messages

# Global variable to track the last processed time
last_processed_time = datetime.min


def handle_request(request, client_address):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # print(f"[{current_time}] Connection from {client_address}")
    """Parse the HTTP request and extract the 'on' or 'off' parameter."""
    try:
        # Split the request into lines and get the first line (request line)
        request_line = request.splitlines()[0]
        
        # print(f"Request:\n{request}\n")
        # print(f"Request Line:\n{request_line}\n")
        # Check if the request line contains the parameter
        if "on" in request_line:
            return "on"
        elif "off" in request_line:
            return "off"
        else:
            return None
    except Exception as e:
        print(f"Error parsing request: {e}\n{request}", file=sys.stderr)
        return None

def handle_connection(client_socket, client_address):
    """Process a single client connection."""
    global last_processed_time

    try:
        # Receive the HTTP request
        request = client_socket.recv(1024).decode('utf-8', errors='replace')  # Decode with error handling
        action = handle_request(request, client_address)
        # print(f"Action: {action}")
        # Check the cooldown
        current_time = datetime.now()
        if current_time - last_processed_time < timedelta(seconds=COOLDOWN_SECONDS):
            # Cooldown active, send a wait message
            wait_response = (
                f"HTTP/1.1 429 Too Many Requests\r\n"
                f"Content-Type: text/plain\r\n\r\n"
                f"Please wait {COOLDOWN_SECONDS} seconds and try again.\n"
           )
            client_socket.sendall(wait_response.encode('utf-8'))
            print(f"Cooldown active for {client_address}. Request ignored.")
        elif action == "on" or action == "off":
        # if action == "on" or action == "off":
            # Process the request and update last processed time
            last_processed_time = current_time
            response = (
                f"HTTP/1.1 200 OK\r\n"
                f"Content-Type: text/plain\r\n\r\n"
                f"Action received: {action}"
            )
            client_socket.sendall(response.encode('utf-8'))

            if action == 'on':
                flag = 'n'
            elif action == 'off':
                flag = 'x'
            else:
                print(f"Bad action: {action}")
                raise(Exception(f"Bad action: {action}"))

            print(f"Action from {client_address}: {action}")
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            data = f'cameraNum=27&audioDevice={flag}'
            url = 'http://mic:Microphone@127.0.0.1:8934/settings-camera'
            print(f"{current_time}: Executing shell script for {action}: curl {data}", file=sys.stderr)
            try:
                subprocess.run(['/usr/bin/curl', '-s', '-d', data, url], check=True)
                print("")
            except subprocess.CalledProcessError as e:
                print(f"Error executing shell script: {e}", file=sys.stderr)

        else:
            # Invalid action
            error_response = (
                f"HTTP/1.1 400 Bad Request\r\n"
                f"Content-Type: text/plain\r\n\r\n"
                f"Invalid action. Use 'on' or 'off'."
            )
            client_socket.sendall(error_response.encode('utf-8'))
#            print(f"Invalid action from {client_address}.")
    except Exception as e:
        print(f"Error handling connection: {e}")
    finally:
        client_socket.close()

def cleanup_and_exit(signum, frame):
    """Handle cleanup when receiving a KeyboardInterrupt (Ctrl+C)."""
    print("\nShutting down server...")
    server_socket.close()
    sys.exit(0)

# Create a socket
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))  # Bind to the specified address and port
    server_socket.listen()            # Enable the server to accept connections
    print(f"Listening on {HOST}:{PORT}...")

    while True:
        try:
            client_socket, client_address = server_socket.accept()
            threading.Thread(target=handle_connection, args=(client_socket, client_address)).start()
        except KeyboardInterrupt:
            print("\nShutting down server...")
            server_socket.close()
            break

exit()


# Register the signal handler for clean shutdown
signal.signal(signal.SIGINT, cleanup_and_exit)


while True:
    # Accept a connection
    client_socket, client_address = server_socket.accept()
    # print(f"Connection detected from {client_address}")
     # Receive the HTTP request
    try:
        request = client_socket.recv(1024).decode('utf-8', errors="ignore")  # Decode the bytes to a string
        
        # Parse the request to determine the parameter
        action = handle_request(request)
    except Exception as e:
        print (f"Failed to parse: {e}", file=sys.stderr)
        continue
    
    # Prepare a simple HTTP response
    if action:
        response = f"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\nAction received: {action}"
#        response = f"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nAction received: {action}"
    else:
        response = "HTTP/1.1 400 Bad Request\r\nContent-Type: text/plain\r\n\r\nInvalid action. Use 'on' or 'off'."
     # Send the response
    client_socket.sendall(response.encode('utf-8'))
    client_socket.close()
    # print(f"Connection closed for {client_address}")
              

    
    # Execute the shell script with the action parameter
    if action:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            subprocess.run(['/usr/bin/curl', '-s', '-d', data, url], check=True)
            print(f"\n{current_time}: Executed shell script for {action}: curl {data}", file=sys.stderr)
        except subprocess.CalledProcessError as e:
            print(f"Error executing shell script: {e}", file=sys.stderr)
