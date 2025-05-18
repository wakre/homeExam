# homeExam
Home Exam – DATA2410
Candidate number: 217

This is my project for the DATA2410 home exam.

A short explanation of how to run app.py to transfer files (for example, an image) between the client and the server. For testing, I used a picture with a size of 23 KB. The application run it in Mininet.

After logging into Mininet, I used xterm h1 and xterm h2 to open terminals for two nodes. One node acts as the server (h2), and the other as the client (h1).

Basic transfer test (without window size and discard):
On the server (h2), I ran this command:
python3 app.py --server --ip 10.0.1.2 --port 8080
This should display: [Server] Listening on 10.0.1.2:8080

On the client (h1), I ran:
python3 app.py --client -f bilde.jpeg --ip 10.0.1.2 --port 8080

Transfer test using a sliding window:
On the server (h2):
python3 app.py --server --ip 10.0.1.2 --port 8080

On the client (h1), using window size 5 (or 10, 15, etc.):
python3 app.py --client -f bilde.jpeg --ip 10.0.1.2 --port 8080 --window 5

Transfer test using packet discard (simulated drop):
On the server (h2), enable discard with this command:
python3 app.py --server --ip 10.0.1.2 --port 8080 --d

On the client (h1):
python3 app.py --client -f bilde.jpeg --ip 10.0.1.2 --port 8080 --window 5
