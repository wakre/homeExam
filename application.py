import socket
import time
import sys
import os
import datetime
import argparse
import struct

# Constants
HEADER_SIZE =  6 # bytes
DATA_SIZE = 994 # bytes
TIMEOUT = 0.4  # seconds (400 ms)

# Flag positions
SYN_FLAG = 0b1000
ACK_FLAG = 0b0100
FIN_FLAG = 0b0010

def pack_header(seq_num, ack_num, flags):
    return struct.pack('!HHH', seq_num, ack_num, flags)

def unpack_header(header_bytes):
    return struct.unpack('!HHH', header_bytes)

# Header packing/unpacking
def build_header(seq_num, ack_num, flags, data_length=0):
    return struct.pack('!HHH', seq_num, ack_num, flags, data_length)

def extract_header(header_bytes):
    return struct.unpack('!HHH', header_bytes)

# Client-Server combined class
class ReliableUDPClientServer:
    def __init__(self, host, port, file_path=None, window_size=None):
        self.host = host
        self.port = port
        self.file_path = file_path
        self.window_size = window_size if window_size else 4
        self.seq_num = 0
        self.ack_num = 0
        self.window_start = 0
        self.window = set()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(TIMEOUT)

    # Client-side functionality
    def start_client_transfer(self):
        try:
            self.sock.connect((self.host, self.port))
            print("[INFO] Starting connection (Client Side)")
            self.initiate_connection()
        except (ConnectionRefusedError, socket.timeout):
            print(f"[ERROR] Server not available at {self.host}:{self.port}")
            self.terminate_connection()
        except Exception as e:
            print("[ERROR] Transfer failed:", e)
            self.terminate_connection()

    def initiate_connection(self):
        try:
            self.seq_num =0 
            self.ack_num = 0 
            header = build_header(self.seq_num, self.ack_num, SYN_FLAG)
            self.sock.send(header)
            print("[SEND] SYN")
            self.wait_for_syn_ack()
        except (socket.timeout, socket.error) as e:
            print("[ERROR] SYN failed:", e)
            self.terminate_connection()

    def wait_for_syn_ack(self):
        try:
            response = self.sock.recv(HEADER_SIZE)
            _, ack_num, flags = extract_header(response)
            if flags & SYN_FLAG and flags & ACK_FLAG:
                print("[RECV] SYN-ACK")
                self.ack_num = ack_num
                self.send_acknowledgment()
        except (socket.timeout, Exception):
            print("[ERROR] No response for SYN-ACK")
            self.terminate_connection()

    def send_acknowledgment(self):
        try:
            header = build_header(self.seq_num, self.ack_num, ACK_FLAG)
            self.sock.send(header)
            print("[SEND] ACK")
            self.transmit_file_data()
        except Exception as e:
            print("[ERROR] Failed to send ACK:", e)
            self.terminate_connection()

    def transmit_file_data(self):
        print("[INFO] Data Transmission Phase (Client Side)")
        with open(self.file_path, 'rb') as f:
            file_data = []
            while True:
                data = f.read(DATA_SIZE)
                if not data:
                    break
                file_data.append(data)

        total_packets = len(file_data)
        next_to_send = 0

        while next_to_send < total_packets or self.window:
            while len(self.window) < self.window_size and next_to_send < total_packets:
                data = file_data[next_to_send]
                header = build_header(next_to_send, self.ack_num, 0)
                self.sock.send(header + data)
                self.window.add(next_to_send)
                print(f"[SEND] Seq={next_to_send} | Window={sorted(self.window)}")
                next_to_send += 1
            self.await_ack(file_data)

        self.initiate_teardown()

    def await_ack(self, file_data):
        try:
            self.sock.settimeout(TIMEOUT)
            response = self.sock.recv(HEADER_SIZE)
            _, ack_num, flags = extract_header(response)
            if flags & ACK_FLAG:
                print(f"[RECV] ACK={ack_num}")
                if ack_num in self.window:
                    self.window.remove(ack_num)
                while self.window_start not in self.window and self.window_start < ack_num:
                    self.window_start += 1
        except socket.timeout:
            print("[TIMEOUT] Retransmitting unacknowledged packets")
            for seq in sorted(self.window):
                data = file_data[seq] if seq < len(file_data) else b''
                pkt = build_header(seq, self.ack_num, 0) + data
                self.sock.send(pkt)
                print(f"[RETRY] Resent Seq={seq}")
        except Exception as e:
            print("[ERROR] ACK receive failed:", e)

    def initiate_teardown(self):
        try:
            header = build_header(self.seq_num, self.ack_num, FIN_FLAG)
            self.sock.send(header)
            print("[SEND] FIN")
            self.receive_teardown_ack()
        except Exception as e:
            print("[ERROR] Sending FIN failed:", e)
            self.terminate_connection()

    def receive_teardown_ack(self):
        try:
            response = self.sock.recv(HEADER_SIZE)
            _, _, flags = extract_header(response)
            if flags & FIN_FLAG and flags & ACK_FLAG:
                print("[RECV] FIN-ACK")
                self.terminate_connection()
        except Exception as e:
            print("[ERROR] Receiving FIN-ACK failed:", e)
            self.terminate_connection()

    def terminate_connection(self):
        print("[CLOSE] Terminating connection")
        try:
            self.sock.close()
            sys.exit(0)
        except Exception:
            sys.exit(1)

    # Server-side functionality
    def start_server(self):
        try:
            self.sock.bind((self.host, self.port))
            print("[INFO] Server started, waiting for connection...")
            self.wait_for_connection()
        except Exception as e:
            print("[ERROR] Server initialization failed:", e)
            self.terminate_connection()

    def wait_for_connection(self):
        try:
            data, addr = self.sock.recvfrom(HEADER_SIZE)
            _, _, flags = extract_header(data)
            if flags & SYN_FLAG:
                print("[RECV] SYN")
                self.send_syn_ack(addr)
                self.receive_ack(addr)
                self.receive_file_data(addr)
        except Exception as e:
            print("[ERROR] Connection failed:", e)
            self.terminate_connection()

    def send_syn_ack(self, addr):
        header = build_header(self.seq_num, self.ack_num, SYN_FLAG | ACK_FLAG)
        self.sock.sendto(header, addr)
        print("[SEND] SYN-ACK")

    def receive_ack(self, addr):
        try:
            data, _ = self.sock.recvfrom(HEADER_SIZE)
            _, ack_num, flags = extract_header(data)
            if flags & ACK_FLAG:
                print("[RECV] ACK")
        except Exception as e:
            print("[ERROR] Failed to receive ACK:", e)
            self.terminate_connection()

    def receive_file_data(self, addr):
        print("[INFO] Receiving Data Phase (Server Side)")
        while True:
            data, _ = self.sock.recvfrom(DATA_SIZE + HEADER_SIZE)
            header = data[:HEADER_SIZE]
            packet_data = data[HEADER_SIZE:]

            seq_num, _, flags = extract_header(header)
            if flags & FIN_FLAG:
                print("[RECV] FIN")
                self.send_fin_ack(addr)
                break

            print(f"[RECV] Data: Seq={seq_num}")
            with open("received_file", 'ab') as f:
                f.write(packet_data)

        self.terminate_connection()

    def send_fin_ack(self, addr):
        header = build_header(self.seq_num, self.ack_num, FIN_FLAG | ACK_FLAG)
        self.sock.sendto(header, addr)
        print("[SEND] FIN-ACK")

    def terminate_connection(self):
        print("[CLOSE] Terminating connection")
        try:
            self.sock.close()
            sys.exit(0)
        except Exception:
            sys.exit(1)


# Helper functions for header packing and unpacking would go here
# Pack header, unpack header, and other utilities




class UDPServer:
    def __init__(self, host, port, discard):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((self.host, self.port))
        self.discard = discard
        self.sock.settimeout(None)

    def start_server(self):
        print("Waiting for connection...")
        self.receive_syn_packet()

    def receive_syn_packet(self):
        try:
            packet, sender_address = self.sock.recvfrom(HEADER_SIZE)
            _, _, flags = unpack_header(packet)

            if flags & SYN_FLAG:
                print("SYN packet received")
                self.send_syn_ack(sender_address)
        except Exception as e:
            print(f"Error receiving SYN packet: {e}")
            print("Closing connection")
            self.close_connection()

    def send_syn_ack(self, sender_address):
        try:
            flags = SYN_FLAG | ACK_FLAG
            syn_ack_packet = pack_header(0, 1, flags)
            self.sock.sendto(syn_ack_packet, sender_address)
            print("SYN-ACK packet is sent")
            self.receive_ack()
        except socket.timeout:
            print("Timeout: No response received for ACK")
            print("Closing connection")
            self.close_connection()
        except socket.error as e:
            print(f"Socket error: {e}")
            print("Closing connection")
            self.close_connection()
        except Exception as e:
            print(f"Error: {e}")
            print("Closing connection")
            self.close_connection()

    def receive_ack(self):
        try:
            received_header, sender_address = self.sock.recvfrom(HEADER_SIZE)
            _, received_ack_num, received_flags = unpack_header(received_header)

            if received_flags & ACK_FLAG:
                print("ACK packet received")
                self.receive_data_packets(sender_address)
        except socket.timeout:
            print("Socket timeout occurred while waiting for ACK packet.")
            print("Closing connection")
            self.close_connection()
        except Exception as e:
            print(f"Error receiving ACK packet: {e}")

    def receive_data_packets(self, sender_address):
        try:
            print("\nConnection Established")
            expected_seq_num = 0
            discard_seq_num = None
            if self.discard:
                discard_seq_num = self.discard
                        
            with open("received_image.jpg", 'wb') as file:
                start_time = time.time()
                while True:
                    received_packet, sender_address = self.sock.recvfrom(HEADER_SIZE + DATA_SIZE)
                    header = received_packet[:HEADER_SIZE]
                    data = received_packet[HEADER_SIZE:]

                    seq_num, ack_num, received_flags = unpack_header(header)

                    if received_flags & FIN_FLAG:
                        break
                    
                    if seq_num == discard_seq_num:
                        current_time = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
                        print(f"{current_time} -- Discarding packet {seq_num}")
                        discard_seq_num = None
                        self.sock.settimeout(None)
                        continue
                    
                    if seq_num == expected_seq_num:
                        current_time = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
                        print(f"{current_time} -- Packet {seq_num} is received")
                        file.write(data)

                        current_time = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
                        print(f"{current_time} -- Sending ACK for the received {seq_num}")
                        ack_header = pack_header(0, seq_num, ACK_FLAG)
                        self.sock.sendto(ack_header, sender_address)
                        expected_seq_num += 1
                    else:
                        self.sock.settimeout(None)
                        current_time = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
                        print(f"{current_time} -- OUT OF ORDER Packet {seq_num} is received")
                        print("Discarded")
                        continue

                    if len(data) < DATA_SIZE:
                        break
                end_time = time.time()
                throughput = (file.tell() * 8) / (end_time - start_time) / 1e6
                print(f"The throughput is {throughput:.2f} Mbps")

            self.receive_fin_packet(sender_address)
        except Exception as e:
            print(f"Error receiving data packets: {e}")

    def receive_fin_packet(self, sender_address):
        try:
            packet, sender_address = self.sock.recvfrom(HEADER_SIZE)
            _, _, flags = unpack_header(packet)

            if flags & FIN_FLAG:
                print("FIN packet received")
                self.send_fin_ack(sender_address)
        except Exception as e:
            print(f"Error receiving FIN packet: {e}")
            print("Closing connection")
            self.close_connection()

    def send_fin_ack(self, sender_address):
        try:
            header = pack_header(0, 0, ACK_FLAG | FIN_FLAG)
            self.sock.sendto(header, sender_address)
            print("FIN ACK packet is sent")
            self.close_connection()
        except socket.error:
            print("Error: Couldn't send FIN ACK packet")
            self.close_connection()
        except Exception as e:
            print(f"Error: {e}")
            self.close_connection()

    def close_connection(self):
        try:
            print("Connection Closed")
            self.sock.close()
            sys.exit(1)
        except socket.error:
            print("Error: Couldn't close socket")
            sys.exit(1)
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)


def parse_arguments():
    parser = argparse.ArgumentParser(description="DRTP File Transfer Application")
    parser.add_argument('-s', '--server', action='store_true', help="Enable server mode")
    parser.add_argument('-c', '--client', action='store_true', help="Enable client mode")
    parser.add_argument('-i', '--ip', type=str, default='127.0.0.1', help="Server IP address (default: 127.0.0.1)")
    parser.add_argument('-p', '--port', type=int, default=8088, help="Port number (default: 8088)")
    parser.add_argument('-f', '--file', type=str, help="File path")
    parser.add_argument('-w', '--window', type=int, default=3, help="Sliding window size (default: 3)")
    parser.add_argument('-d', '--discard', type=int, help="Custom test case to skip a sequence number")
    return parser.parse_args()


def main():
    args = parse_arguments()

    if args.server:
        server = UDPServer(args.ip, args.port, args.discard)
        server.start_server()
    elif args.client:
         if not args.file:
            print("Error: Please specify the file path using -f when in client mode.")
            sys.exit(1)
         client = ReliableUDPClientServer(args.ip, args.port, file_path=args.file, window_size=args.window)
         client.start_client_transfer()

    else:
        print("Error: Please specify either server (-s) or client (-c) mode.")
        sys.exit(1)


if __name__ == "__main__":
    main()
