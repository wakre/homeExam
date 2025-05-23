import socket
import os
import time
import argparse
from struct import pack, unpack #for packing/unpacking binary header 

# --- Packet Header ---
# header is 8 bytes total: seq (4), ack (2), flags (1), window (1)
HEADER_FORMAT = '!IHBB'
HEADER_SIZE = 8 

# --- Client ---
"""The DRTPClient class is responsible for sending a file over UDP using a custom protocol 
that mimics many behaviors of TCP.

Key functionalities include:
- Establishing a connection with the server using a 3-way handshake.
- Reading and sending the file in chunks.
- Ensuring reliability using a sliding window mechanism.
- Handling acknowledgments (ACKs).
- Resending lost packets after a timeout."""
class DRTPClient:
    
    # This function creates a UDP socket for sending data
    def __init__(self, file_path, server_ip, server_port, window_size):
        self.file_path = file_path
        self.server_ip = server_ip
        self.server_port = server_port
        self.window_size = window_size
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(2)

    # This function creates a packet by building an 8-byte header and returns the complete packet with the header.
    def create_packet(self, seq, ack, flags, win, data):
        header = pack(HEADER_FORMAT, seq, ack, flags, win)
        return header + data
        
    #Handles SYN, ACK, FIN flag control and sends the packet to the server with flags converted to binary.
    def send_control(self, flag_name):
        flags = {"SYN": 0b1000, "ACK": 0b0100, "FIN": 0b0010, "FIN_ACK": 0b0110}.get(flag_name, 0)
        packet = self.create_packet(0, 0, flags, 0, b'')
        self.sock.sendto(packet, (self.server_ip, self.server_port))
    #This function waits to receive a packet with a specific flag (e.g., SYN-ACK, FIN-ACK), unpacks the header, checks if the flags match, and returns False on timeout.
    def wait_for_response(self, expected_flag_name):
        expected_flag = {"SYN-ACK": 0b1100, "FIN_ACK": 0b0110}[expected_flag_name]
        try:
            data, _ = self.sock.recvfrom(1024)
            _, _, flags, _ = unpack(HEADER_FORMAT, data[:HEADER_SIZE])
            return flags == expected_flag
        except socket.timeout:
            return False
    # This function sends a SYN packet, waits for a SYN-ACK response, and then sends an ACK to complete the 3-way handshake, mimicking TCP.
    def start_handshake(self):
        self.send_control("SYN")
        print("SYN packet is sent")
        if self.wait_for_response("SYN-ACK"):
            print("SYN-ACK packet is received")
            self.send_control("ACK")
            print("ACK packet sent\nConnection established")
    # This function sends a FIN packet to indicate the end of transmission, waits for a FIN-ACK from the server, and then closes the socket.
    def terminate_connection(self):
        self.send_control("FIN")
        print("FIN packet sent")
        if self.wait_for_response("FIN_ACK"):
            print("FIN ACK packet is received\nConnection closes")

    def start_client(self):
        # this function is for starting the file transfer process
        # first, it checks if the file exists, if not it prints an error and exits     
        if not os.path.isfile(self.file_path):
            print(f"[!] File not found: {self.file_path}")
            return
        # performs the 3-way handshake with the server before starting transmission
        self.start_handshake()
        start_time = time.time()
        
        # opens the file in binary read mode and initializes sliding window parameters
        with open(self.file_path, "rb") as f:
            base = 0
            next_seq = 0
            window = {}
            finished = False
            
           # Here is the main loop: keeps running while there is data to send or unacknowledged packets in the window
            while not finished or window:
                while len(window) < self.window_size and not finished:  # send packets until window is full or the file ends
                    data = f.read(992)
                    if not data:
                        finished = True
                        break
                    # create a packet with the current sequence number
                    packet = self.create_packet(next_seq, 0, 0, 0, data)
                    self.sock.sendto(packet, (self.server_ip, self.server_port)) # send the packet to the server
                    print(f"[Client] Sent packet {next_seq}")
                    window[next_seq] = (packet, time.time())
                    next_seq += 1

                try:
                    # wait to receive an ACK from the server
                    ack_data, _ = self.sock.recvfrom(1024)
                    ack_seq, _, flags, _ = unpack(HEADER_FORMAT, ack_data[:HEADER_SIZE])
                    if flags == 0b0100 and ack_seq in window:
                        print(f"[Client] Received ACK for packet {ack_seq}")
                        del window[ack_seq]
                except socket.timeout:
                    # if timeout happens, resend all unacknowledged packets
                    print("[Client] Timeout. Resending unacked packets...")
                    for seq_num, (packet, _) in list(window.items()):
                        self.sock.sendto(packet, (self.server_ip, self.server_port))
                        print(f"[Client] Resent packet {seq_num}")
        # calculate and prints the file transfer duration and throughput in Mbps
        end_time = time.time()
        duration = end_time - start_time
        file_size = os.path.getsize(self.file_path) * 8
        throughput_mbps = file_size / (duration * 1_000_000)
        print(f"[Client] File transfer completed in {duration:.2f} seconds")
        print(f"[Client] Throughput: {throughput_mbps:.2f} Mbps")

        self.terminate_connection()
        self.sock.close()


# --- Server ---
class DRTPServer:
    def __init__(self, ip, port, discard=False):
        # this function initializes the server with the given IP and port
        # it also creates a UDP socket and binds it to start listening
        self.ip = ip
        self.port = port
        self.discard = discard
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((ip, port))
        print(f"[Server] Listening on {ip}:{port}")

    def parse_header(self, packet):
        # this function extracts and returns header fields from the received packet
        return unpack(HEADER_FORMAT, packet[:HEADER_SIZE])

    def send_ack(self, addr, seq):
        # this function sends an ACK packet with the given sequence number to the client
        ack_packet = pack(HEADER_FORMAT, seq, 0, 0b0100, 0)
        self.sock.sendto(ack_packet, addr)

    def handle_handshake(self):
        # this function handles the the 3-way handshake with the client
        while True:
            data, addr = self.sock.recvfrom(1024)
            _, _, flags, _ = self.parse_header(data)
            if flags == 0b1000:
                print("SYN packet is received")
                # send SYN-ACK back to the client
                syn_ack = pack(HEADER_FORMAT, 0, 0, 0b1100, 0)
                self.sock.sendto(syn_ack, addr)
                print("SYN-ACK packet is sent")
                # wait for final ACK to complete handshake
                ack_data, _ = self.sock.recvfrom(1024)
                _, _, ack_flags, _ = self.parse_header(ack_data)
                if ack_flags == 0b0100:
                    print("ACK packet is received\nConnection established")
                    return addr

    def handle_termination(self, data, addr):
        # this function handles the connection termination (FIN-ACK exchange)
        _, _, flags, _ = self.parse_header(data)
        if flags == 0b0010: #checking for FIN flag
            print("FIN packet is received")
            fin_ack = pack(HEADER_FORMAT, 0, 0, 0b0110, 0) # send FIN-ACK to the client
            self.sock.sendto(fin_ack, addr)
            print("FIN ACK packet is sent")

    def start_server(self):
        # this function starts the server to receive and write incoming packets
        expected_seq = 0
        dropped_once = False
        with open("received_file", "wb") as f:
            while True:
                try:
                    # receive a packet from the client
                    packet, addr = self.sock.recvfrom(2048)
                    seq, _, _, _ = self.parse_header(packet)
                    data = packet[HEADER_SIZE:]

                    if self.discard and not dropped_once and seq == expected_seq:
                        print(f"[Server] Simulating drop for packet {seq}")
                        dropped_once = True
                        continue

                    if seq == expected_seq: # write the data to the file if the sequence number matches
                        f.write(data)
                        print(f"{time.strftime('%H:%M:%S')} -- packet {seq} is received")
                        self.send_ack(addr, seq)
                        print(f"{time.strftime('%H:%M:%S')} -- sending ack for the received {seq}")
                        expected_seq += 1
                    else:
                        print(f"{time.strftime('%H:%M:%S')} -- Unexpected seq {seq}, expected {expected_seq}")
                        self.send_ack(addr, expected_seq - 1)
                except KeyboardInterrupt: # allow server to stop with Ctrl+C
                    print("\n[Server] Interrupted. Exiting.")
                    break


# --- Argparse Wrapper ---
def parse_args():
    # this function parses command-line arguments for server/client configuration
    parser = argparse.ArgumentParser(description="DRTP UDP File Transfer")
    parser.add_argument("-s", "--server", action="store_true", help="Run in server mode")
    parser.add_argument("-c", "--client", action="store_true", help="Run in client mode")
    parser.add_argument("-f", "--file", type=str, help="File to send (client mode)")
    parser.add_argument("-ip", "--ip", type=str, default="127.0.0.1", help="IP address")
    parser.add_argument("-p", "--port", type=int, default=8080, help="Port number")
    parser.add_argument("-w", "--window", type=int, default=5, help="Sliding window size")
    parser.add_argument("-d", "--discard", action="store_true", help="Simulate packet drop (server mode)")
    return parser.parse_args()


def main(): 
    # this function decides whether to run the server or client based on args
    args = parse_args()

    if args.server:
        server = DRTPServer(args.ip, args.port, discard=args.discard)
        server.start_server()
    elif args.client:
        if not args.file:
            print("[!] You must specify a file using -f")
            return
        client = DRTPClient(args.file, args.ip, args.port, window_size=args.window)
        client.start_client()
    else:
        print("[!] Must specify either --server or --client")


if __name__ == "__main__":
    main()
