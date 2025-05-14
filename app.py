import socket
import os
import time
import argparse


class DRTPClient:
    def __init__(self, file_path, server_ip, server_port):
        self.file_path = file_path
        self.server_ip = server_ip
        self.server_port = server_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(2)

    def send_packet(self, data, seq):
        header = f"{seq:08}".encode()
        self.sock.sendto(header + data, (self.server_ip, self.server_port))

    def wait_for_ack(self, seq):
        try:
            ack, _ = self.sock.recvfrom(1024)
            ack_seq = int(ack.decode())
            return ack_seq == seq
        except socket.timeout:
            return False

    def start_client(self):
        if not os.path.isfile(self.file_path):
            print(f"[!] File not found: {self.file_path}")
            return

        with open(self.file_path, "rb") as f:
            seq = 0
            while True:
                data = f.read(1024)
                if not data:
                    break

                self.send_packet(data, seq)
                print(f"[Client] Sent packet {seq}")

                while not self.wait_for_ack(seq):
                    print(f"[Client] Timeout on packet {seq}, retransmitting...")
                    self.send_packet(data, seq)

                seq += 1

        print("[Client] File transfer complete")
        self.sock.close()
class DRTPServer:
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((ip, port))
        print(f"[Server] Listening on {ip}:{port}")

    def send_ack(self, addr, seq):
        ack = f"{seq:08}".encode()
        self.sock.sendto(ack, addr)

    def start_server(self):
        expected_seq = 0
        with open("received_file", "wb") as f:
            while True:
                try:
                    packet, addr = self.sock.recvfrom(2048)
                    seq = int(packet[:8].decode())
                    data = packet[8:]

                    if seq == expected_seq:
                        f.write(data)
                        print(f"[Server] Received packet {seq}, sending ACK")
                        self.send_ack(addr, seq)
                        expected_seq += 1
                    else:
                        print(f"[Server] Unexpected seq {seq}, expected {expected_seq}, sending last ACK")
                        self.send_ack(addr, expected_seq - 1)
                except KeyboardInterrupt:
                    print("\n[Server] Interrupted. Exiting.")
                    break 
def parse_args():
    parser = argparse.ArgumentParser(description="DRTP UDP File Transfer")
    parser.add_argument("-s", "--server", action="store_true", help="Run in server mode")
    parser.add_argument("-c", "--client", action="store_true", help="Run in client mode")
    parser.add_argument("-f", "--file", type=str, help="File to send (client mode)")
    parser.add_argument("-ip", "--ip", type=str, default="127.0.0.1", help="IP address")
    parser.add_argument("-p", "--port", type=int, default=8080, help="Port number")
    return parser.parse_args()

def main():
    args = parse_args()

    if args.server:
        server = DRTPServer(args.ip, args.port)
        server.start_server()
    elif args.client:
        if not args.file:
            print("[!] You must specify a file using -f")
            return
        client = DRTPClient(args.file, args.ip, args.port)
        client.start_client()
    else:
        print("[!] Must specify either --server or --client")

if __name__ == "__main__":
    main()
