import socket
import wave
import time
import os
import json
import concurrent.futures
from datetime import datetime


# Define the server address and ports
UDP_IP = "localhost"
RTP_PORT = 5059  # RTP streaming port
SIP_PORT = 5059  # SIP signaling port


# Load SIP signals from JSON file
def load_sip_signals(json_file):
    try:
        with open(json_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading JSON file: {e}")
        return {}


# Send SIP INVITE and wait for 200 OK
def send_sip_invite_and_wait_for_ok(ip, port, sip_invite):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(5)  # Timeout for waiting for 200 OK

    invite_timestamp = datetime.now()
    sock.sendto(sip_invite.encode(), (ip, port))
    print(f"Sent SIP INVITE at {invite_timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]} to {ip}:{port}")

    try:
        data, addr = sock.recvfrom(4096)  # Buffer size is 4096 bytes for SIP signaling
        ok_timestamp = datetime.now()
        duration_ms = (ok_timestamp - invite_timestamp).total_seconds() * 1000

        if data.startswith(b"SIP/2.0 200 OK"):
            print("\n\nSIP INVITE APPROVED, RECEIVED SIGNAL AS BELOW - \n", data.decode(), "\n\n")
            print(f"Received 200 OK from {addr} at {ok_timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
            print(f"Duration to receive 200 OK: {duration_ms:.2f} ms")
            return True
        else:
            print("Unexpected response:", data.decode())
            return False
    except socket.timeout:
        print("Timeout waiting for 200 OK")
        return False


# Direct the audio file to the UDP port
def send_audio_file(ip, port, audio_file):
    try:
        # Create a UDP socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Open the audio file
        with wave.open(audio_file, 'rb') as wf:
            # Get audio file parameters
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            frame_rate = wf.getframerate()
            n_frames = wf.getnframes()
            print(f"\nAudio file parameters: channels={channels}, sample_width={sample_width}, frame_rate={frame_rate}, n_frames={n_frames}")

            # Read and send audio data
            chunk_size = 16384
            while True:
                data = wf.readframes(chunk_size)
                if not data:
                    break
                sock.sendto(data, (ip, port))
                time.sleep(chunk_size / frame_rate)

        sock.close()
    except Exception as e:
        print(f"Error sending audio file {audio_file}: {e}")


# Stream SIP signal and audio concurrently for each entry
def stream_signal_and_audio(path, sip_signal):
    print(f"---------------------------------------------------------------------------------------------------------")
    print(f"Attempting to stream audio file: {path}")

    if send_sip_invite_and_wait_for_ok(UDP_IP, SIP_PORT, sip_signal):
        send_audio_file(UDP_IP, RTP_PORT, path)
        print(f"\nFile stream complete for {path}")
    else:
        print("Failed to receive 200 OK, skipping audio streaming")

def main():
    json_file = "/home/aiadmin/hsbc-cca/SIPjson.json"
    sip_signals = load_sip_signals(json_file)

    if not sip_signals:
        print("No SIP signals found. Please check the JSON file.")
        return

    # Create a thread pool for concurrent processing
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = []
        for folder_path, sip_signal_list in sip_signals.items():
            folder_path = folder_path.strip()  # Remove leading and trailing whitespace
            print(f"Checking folder path: '{folder_path}'")  # Debugging output

            try:
                audio_files = [f for f in os.listdir(folder_path) if f.endswith('.wav')]
                for index, audio_file in enumerate(audio_files):
                    audio_file_path = os.path.join(folder_path, audio_file)
                    print(f"Checking audio file at path: {audio_file_path}")

                    if os.path.isfile(audio_file_path):
                        # Use the SIP signal at the current index, cycling if necessary
                        sip_signal = sip_signal_list[index % len(sip_signal_list)]
                        futures.append(executor.submit(stream_signal_and_audio, audio_file_path, sip_signal))
                    else:
                        print(f"Audio file does not exist or is not a .wav file: {audio_file_path}")
            except FileNotFoundError as e:
                print(f"Error: {e}")

        # Wait for all futures to complete
        for future in concurrent.futures.as_completed(futures):
            future.result()  # Get the result to raise exceptions if any occurred

    print("All files streamed successfully")

if __name__ == "__main__":
    main()