import socket
import pjsua2 as pj

# Declare call_id as a global variable
call_id = None

# PJSUA2 config function
def create_transport(endpoint):
    transport_config = pj.TransportConfig()
    transport = endpoint.transportCreate(pj.PJSIP_TRANSPORT_UDP, transport_config)
    return transport

# PJSUA2 instance initialization function
def initialize_pjsua2():
    endpoint = pj.Endpoint()
    try:
        endpoint.libCreate()
        
        ep_config = pj.EpConfig()
        endpoint.libInit(ep_config)
        
        create_transport(endpoint)
        
        endpoint.libStart()
        print("PJSUA2 initialized and started successfully")
        
        return endpoint
    
    except pj.Error as e:
        print(f"PJSUA2 initialization error: {e}")
        return None
    
# PJSUA2 cleanup function
def cleanup_pjsua2(endpoint):
    endpoint.libDestroy()
    print("PJSUA2 cleanup completed")

# Generate a realistic SIP 200 OK response
def generate_sip_200_ok(call_id, cseq):
    sip_200_ok = (
        "SIP/2.0 200 OK\r\n"
        "Via: SIP/2.0/TCP sbc.domain.com;branch=z9hG4bK8ej5gf0048h2al8c1j60\r\n"
        "To: <sip:receiver@domain.com>;tag=1928301774\r\n"
        f"From: \"caller\" <sip:caller@domain.com>;tag=1928301774\r\n"
        f"Call-ID: {call_id}\r\n"
        f"CSeq: {cseq} INVITE\r\n"
        "Contact: <sip:receiver@domain.com>\r\n"
        "Content-Type: multipart/mixed; boundary=unique-boundary-1\r\n"
        "Content-Length: 142\r\n"
        "\r\n"
        "--unique-boundary-1\r\n"
        "Content-Type: application/sdp\r\n"
        "\r\n"
        "v=0\r\n"
        "o=receiver 53655765 2353687637 IN IP4 pc33.atlanta.com\r\n"
        "s=-\r\n"
        "c=IN IP4 pc33.atlanta.com\r\n"
        "t=0 0\r\n"
        "m=audio 3456 RTP/AVP 0\r\n"
        "a=rtpmap:0 PCMU/8000\r\n"
        "\r\n"
        "--unique-boundary-1\r\n"
        "Content-Type: application/rs-metadata+xml\r\n"
        "Content-Disposition: recording-session\r\n"
        "\r\n"
        "<?xml version='1.0' encoding='UTF-8'?>\r\n"
        "<recording xmlns='urn:ietf:params:xml:ns:recording'>\r\n"
        "    <datamode>complete</datamode>\r\n"
        "    <session id=\"6u4XTLrGSfZ8+6XJ3gRtKQ==\">\r\n"
        "        <associate-time>2024-06-14T15:00:11</associate-time>\r\n"
        "        <extensiondata xmlns:apkt=http://acmepacket.com/siprec/extensiondata>\r\n"
        "            <apkt:ucid>00PNOK199KB5J0CSL8RQ305AES00GCL6</apkt:ucid>\r\n"
        "            <apkt:callerOrig>true</apkt:callerOrig>\r\n"
        "        </extensiondata>\r\n"
        "    </session>\r\n"
        "</recording>\r\n"
        "--unique-boundary-1--\r\n"
    )
    return sip_200_ok

# Handle SIP INVITE and respond with 200 OK
def handle_sip_invite(sock, data, addr):
    global call_id  # Declare call_id as global to modify its value
    lines = data.decode().split("\r\n")
    
    cseq = ""
    for line in lines:
        if line.startswith("Call-ID:"):
            call_id = line.split(":")[1].strip()  # Extract Call-ID properly
        if line.startswith("CSeq:"):
            cseq = line.split(":")[1].strip()  # Extract CSeq properly
    
    # Generate and send the 200 OK response
    sip_200_ok = generate_sip_200_ok(call_id, cseq)
    sock.sendto(sip_200_ok.encode(), addr)
    print(f"Sent 200 OK to {addr}")
    print(f"Parsed Call-ID: {call_id}")  # Print the parsed Call-ID for debugging

# UDP server function
def udp_server(ip, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # Reuse address
    sock.bind((ip, port))
    print(f"UDP server started at {ip}:{port}")

    while True:
        data, addr = sock.recvfrom(16384)  # Buffer size is 16384 bytes
        if data.startswith(b"INVITE"):
            print(f"Received SIP INVITE from {addr}")
            handle_sip_invite(sock, data, addr)
        else:
            print(f"Received {len(data)} bytes from {addr} for callID - {call_id}")  # Print call_id here
            response = f"Received {len(data)} bytes"
            sock.sendto(response.encode('utf-8'), addr)

# Main function to initialize PJSUA2 and start UDP server
def main():
    endpoint = initialize_pjsua2()
    if not endpoint:
        return

    udp_port = 5059
    udp_ip = "localhost"
    try:
        udp_server(udp_ip, udp_port)

    except OSError as e:
        if e.errno == 98:
            print(f"Error: Port {udp_port} is already in use.")
            print("Please ensure no other application is using this port.")
        else:
            print(f"Error: {e}")

    except KeyboardInterrupt:
        print("UDP server stopped")

    finally:
        cleanup_pjsua2(endpoint)

if __name__ == "__main__":
    main()