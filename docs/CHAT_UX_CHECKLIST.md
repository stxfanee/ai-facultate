# Chat UX verification checklist

Use this checklist after changes to the chat interface.

## Auto-scroll

- Send a new message in a browser session. The view scrolls to the newest user message.
- While the assistant streams, the latest generated text remains visible.
- When generation finishes, the final assistant message remains visible.
- Scroll up during generation. The page does not force-scroll away from older messages.
- Confirm the floating **? Latest** button appears after scrolling up.
- Click **? Latest**. The page jumps to the newest message and resumes auto-scroll.
- Repeat the same checks in the desktop WebView app.
- Repeat in Server Mode and Client Mode when available.

## Queue recovery

- Start a request and close/restart the UI before it finishes.
- Send a new request after restart. Old abandoned queued requests should not block the GPU slot.
- Confirm Server Status reports zero queued/running requests after completion.
