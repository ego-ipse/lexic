import datetime

def log_session_end():
    now = datetime.datetime.now()
    message = f"Session ended successfully at: {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
    print(message)
    with open("session_log.txt", "a") as f:
        f.write(message)

if __name__ == "__main__":
    log_session_end()
