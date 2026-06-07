import threading
import webview
from app import app  

def start_flask():
    app.run(debug=False, port=5000)

if __name__ == '__main__':
    t = threading.Thread(target=start_flask)
    t.daemon = True
    t.start()

    window = webview.create_window(
        "ForelForge", 
        "http://127.0.0.1:5000/", 
        min_size=(800, 600) 
    )
    webview.start()