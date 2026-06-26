# Instalare Copilot Facultate pe Windows

Acest client este un launcher nativ Windows. El nu recreeaza interfata in
Tkinter si nu ruleaza AI local. Deschide interfata Streamlit a serverului intr-o
fereastra WebView2 fara bara de adresa.

Clientul nu ruleaza Ollama, nu descarca modele AI si nu creeaza ChromaDB.

## 1. Porneste serverul pe desktop

Pe PC-ul desktop:

1. Porneste Ollama.
2. Deschide folderul proiectului `ai-facultate-code`.
3. Ruleaza:

```text
start_server.bat
```

Serverul porneste:

- Streamlit UI pe portul `8501`;
- FastAPI pe portul `8000`.

Pentru clientul nativ folosesti URL-ul Streamlit, adica portul `8501`.

## 2. Afla URL-ul Streamlit al serverului

Pe desktop:

```text
http://localhost:8501
```

Pe laptop, foloseste adresa desktopului:

```text
http://ADRESA_LAN:8501
http://ADRESA_TAILSCALE:8501
```

Exemplu Tailscale:

```text
http://100.x.y.z:8501
```

Recomandat: Tailscale. Nu expune portul direct pe internet si nu folosi port
forwarding public.

## 3. Creeaza executabilul client

Pe desktopul unde ai proiectul:

```text
build_client.bat
```

La final apare:

```text
dist\Copilot Facultate.exe
```

Copiaza acest fisier pe laptopul Windows.

## 4. Prima pornire pe laptop

Pe laptop:

1. Deschide `Copilot Facultate.exe`.
2. La prima pornire introdu URL-ul Streamlit al serverului:

```text
http://100.x.y.z:8501
```

3. Apasa `Salveaza si deschide`.

Launcherul memoreaza URL-ul local in profilul utilizatorului Windows si apoi
deschide direct interfata Streamlit la urmatoarele porniri.

## 5. Resetarea URL-ului salvat

Daca ai introdus URL-ul gresit, porneste aplicatia din PowerShell cu:

```powershell
.\Copilot Facultate.exe --reset
```

Sau sterge fisierul:

```text
%APPDATA%\Copilot Facultate\settings.json
```

## WebView2

Launcherul foloseste Microsoft Edge WebView2. Pe Windows 11 este deja instalat
in mod normal. Daca aplicatia nu porneste pe un Windows mai vechi, instaleaza
Microsoft Edge WebView2 Runtime de pe site-ul Microsoft.

## Installer optional cu Inno Setup

Daca vrei un installer clasic `.exe`:

1. Instaleaza Inno Setup pe un PC Windows.
2. Creeaza un script Inno Setup nou.
3. La `Application main executable file`, selecteaza:

```text
dist\Copilot Facultate.exe
```

4. Alege numele aplicatiei:

```text
Copilot Facultate
```

5. Compileaza installerul.

Installerul rezultat poate fi copiat pe laptopuri Windows. Nu include Ollama,
modele AI sau ChromaDB.

## Reguli importante

- Serverul AI ramane pe desktop.
- Laptopul ruleaza doar launcherul WebView2.
- Interfata este Streamlit-ul serverului, identica cu desktopul.
- Nu instala Ollama pe laptop pentru acest client.
- Nu descarca modele AI pe laptop.
- Nu expune serverul direct pe internet.
- Pentru remote access foloseste Tailscale.
