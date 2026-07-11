# Instalare Co-pilot Facultate pe Windows

Acest client este un launcher nativ Windows. El nu recreeaza interfata in
Tkinter si nu ruleaza AI local. Deschide interfata Streamlit a serverului intr-o
fereastra WebView2 fara bara de adresa.

Clientul nu ruleaza Ollama, nu descarca modele AI si nu creeaza ChromaDB.
Mai multi utilizatori pot folosi simultan acelasi desktop. Daca GPU-ul este
ocupat, interfata afiseaza pozitia in coada si ramane responsiva.

## 1. Porneste serverul pe desktop

Pe PC-ul desktop:

1. Porneste Ollama.
2. Deschide folderul proiectului `ai-facultate-code`.
3. Ruleaza:

```text
start_server.bat
```

Autentificarea este dezactivată implicit pentru testare: clientul intră direct
în spațiul comun `default_user`. Nu trebuie creat niciun cont. Pentru a activa
mai târziu conturile separate, pornește serverul cu
`FACULTY_COPILOT_AUTH_ENABLED=1`, apoi creează utilizatorul:

```powershell
.\.venv\Scripts\python.exe manage_users.py nume --password "parola-lunga"
```

Serverul porneste:

- Streamlit UI pe portul `8501`;
- FastAPI pe portul `8000`.

Pentru setup introduci URL-ul serverului API, adica portul `8000`. Launcherul
va deschide automat Streamlit pe portul `8501`.

## 2. Afla URL-ul serverului

Pe desktop:

```text
http://localhost:8000
```

Pe laptop, foloseste adresa desktopului:

```text
http://ADRESA_LAN:8000
http://ADRESA_TAILSCALE:8000
```

Exemplu Tailscale:

```text
http://100.x.y.z:8000
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
dist\Co-pilot Facultate.exe
```

Copiaza acest fisier pe laptopul Windows sau descarca-l din GitHub Release-ul
publicat de administratorul serverului. Utilizatorul nou nu instaleaza Python.

## 4. Prima pornire pe laptop

Pe laptop:

1. Deschide `Co-pilot Facultate.exe`.
2. La prima pornire introdu URL-ul serverului desktop:

```text
http://ADRESA_LAN_SAU_TAILSCALE:8000
```

3. Apasa `Test connection`.
4. Apasa `Save`.
5. Apasa `Open app`.
6. Cu autentificarea implicit dezactivată, Streamlit se deschide direct în
   spațiul `default_user`. Dacă administratorul a activat autentificarea,
   introdu utilizatorul și parola/tokenul primit.
7. Folosește `Alege fișiere de pe acest dispozitiv`; uploaderul citește
   laptopul, nu deschide selectorul de fișiere pe desktopul server.

Launcherul memoreaza URL-ul local in profilul utilizatorului Windows in
`config.json`. La urmatoarele porniri, deschide automat interfata Streamlit a
serverului. Daca introduci portul API `8000`, launcherul testeaza conexiunea pe
`/health` si deschide automat Streamlit pe portul `8501`.

Din meniu poti folosi `Copilot -> Setari server` pentru a schimba URL-ul mai
tarziu.

## 5. Resetarea URL-ului salvat

Daca ai introdus URL-ul gresit, porneste aplicatia din PowerShell cu:

```powershell
.\Co-pilot Facultate.exe --reset
```

Sau sterge fisierul:

```text
%APPDATA%\Copilot Facultate\config.json
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
dist\Co-pilot Facultate.exe
```

4. Alege numele aplicatiei:

```text
Co-pilot Facultate
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
- În modul fără autentificare, clienții folosesc împreună `default_user`.
- În modul cu autentificare, fiecare cont are documente, Chroma namespace și
  memorie SQLite separate.
- Daca apare mesajul cu pozitia in coada, lasa aplicatia deschisa; generarea
  porneste automat cand slotul GPU devine liber.
