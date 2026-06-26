# Instalare client Windows

Acest client este doar interfata pentru laptop. Nu ruleaza Ollama, nu descarca
modele AI si nu creeaza ChromaDB. Toata inferenta AI ramane pe desktopul server
cu RTX 3070.

## 1. Porneste serverul pe desktop

Pe PC-ul desktop:

1. Porneste Ollama.
2. Deschide folderul proiectului `ai-facultate-code`.
3. Ruleaza:

```text
start_server.bat
```

Serverul FastAPI porneste implicit pe portul `8000`.

Pentru acces din afara retelei de acasa, foloseste Tailscale. Nu face port
forwarding public in router.

## 2. Afla adresa serverului

Pe desktop, adresa poate fi:

```text
http://localhost:8000
```

Pe laptop, foloseste una dintre adresele desktopului:

```text
http://ADRESA_LAN:8000
http://ADRESA_TAILSCALE:8000
```

Exemplu Tailscale:

```text
http://100.x.y.z:8000
```

## 3. Creeaza aplicatia client .exe

Pe desktopul unde ai proiectul:

```text
build_client.bat
```

La final apare:

```text
dist\AI Study Copilot Client.exe
```

Copiaza acest fisier pe laptopul Windows.

## 4. Porneste clientul pe laptop

Pe laptop:

1. Deschide `AI Study Copilot Client.exe`.
2. Introdu adresa serverului, de exemplu:

```text
http://100.x.y.z:8000
```

3. Optional, completeaza username.
4. Lasa bifat `Remember server`.
5. Apasa `Test`.
6. Foloseste taburile:

- `Intrebari`
- `Flashcards`
- `Quiz`
- `Progres`
- `Plan sesiune`

Setarile clientului sunt salvate local in Windows, in profilul utilizatorului.

## HTTPS optional

HTTP prin Tailscale este de obicei suficient pentru uz privat, deoarece traficul
Tailscale este criptat in reteaua privata.

Daca ai certificat TLS pentru server, seteaza pe desktop:

```powershell
$env:FACULTY_COPILOT_SSL_CERTFILE = "C:\cale\cert.pem"
$env:FACULTY_COPILOT_SSL_KEYFILE = "C:\cale\key.pem"
.\start_server.bat
```

In client foloseste:

```text
https://ADRESA_TAILSCALE:8000
```

Daca folosesti un certificat self-signed, debifeaza `Verify HTTPS` doar daca ai
incredere in acel server.

## Installer optional cu Inno Setup

Daca vrei un installer clasic `.exe`:

1. Instaleaza Inno Setup pe un PC Windows.
2. Creeaza un script Inno Setup nou.
3. La `Application main executable file`, selecteaza:

```text
dist\AI Study Copilot Client.exe
```

4. Alege numele aplicatiei:

```text
AI Study Copilot Client
```

5. Compileaza installerul.

Installerul rezultat poate fi copiat pe laptopuri Windows. Nu include Ollama,
modele AI sau ChromaDB.

## Reguli importante

- Serverul AI ramane pe desktop.
- Laptopul ruleaza doar clientul.
- Nu instala Ollama pe laptop pentru acest client.
- Nu descarca modele AI pe laptop.
- Nu expune serverul direct pe internet.
- Pentru remote access foloseste Tailscale.
