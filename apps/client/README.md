# Faculty Copilot desktop client

This folder contains the Windows desktop client wrapper. It is intentionally only a client:

- no Ollama
- no ChromaDB
- no local AI models
- no local document index

The app opens the remote Faculty Copilot web interface inside a native WebView2 window, keeps server-side cookies between launches, and stores only local client settings such as the server URL and window size.
