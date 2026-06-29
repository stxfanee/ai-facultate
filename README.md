# Faculty Copilot v0.4

Aplicatie locala pentru facultate, construita peste documentele tale indexate.

Faculty Copilot v0.4 extinde asistentul RAG intr-un copilot academic local:
organizeaza cursurile pe `An -> Materie -> Curs`, retine progresul in SQLite
si genereaza planuri realiste de sesiune cu export local `.ics`.

Aceasta functie nu antreneaza si nu modifica modelul Qwen. Nu exista
fine-tuning. Aplicatia salveaza numai progresul, metadatele si planurile tale
intr-o baza SQLite locala.

## Ce face

- Ruleaza din folderul proiectului, fara cai hardcodate.
- Creeaza `documents/`, `storage/`, baza ChromaDB si memoria SQLite in proiect.
- În modul local selectează documente prin dialog nativ Windows; în modul remote
  încarcă fișierele din browserul clientului.
- Indexeaza PDF, DOCX si PPTX in ChromaDB.
- Răspunde automat prin RAG, cunoștințe generale sau o combinație a celor două.
- Afiseaza lista completa de documente indexate.
- Organizeaza documentele pe `An -> Materie -> Curs`.
- Permite editarea metadatelor academice pentru fiecare document indexat.
- Detecteaza intrebari despre un curs anume, de exemplu `despre ce este cursul 1`.
- Filtreaza retrieval-ul la documentul cerut cand intrebarea mentioneaza un curs/PDF.
- Pastreaza retrieval semantic global pentru intrebari de continut.
- Ofera moduri de raspuns `Fast`, `Balanced` si `Accurate`.
- Foloseste o interfata de chat cu conversatii locale persistente, cautare si surse
  pastrate sub fiecare raspuns.
- Ruteaza hibrid intre RAG-ul cursurilor si cunostintele generale ale modelului.
- Afiseaza raspunsul progresiv in timp ce Ollama genereaza textul.
- Memoreaza temporar retrieval-urile repetate si elimina contextul redundant.
- Grupeaza intrebarile, comparatiile, rezumatele si cautarea intr-un document
  intr-un singur tab `Intrebari`.
- Genereaza flashcards si quiz-uri interactive.
- Retine local intrebarile, documentele studiate si sursele folosite.
- Retine subiectele marcate `greu`, `neclar` sau `de repetat`.
- Salveaza raspunsurile si scorurile quizurilor.
- Genereaza planuri de sesiune pe zile, cu recapitulare si quiz-uri.
- Exporta planul de sesiune ca fisier calendar `.ics`, local.
- Salveaza planurile generate in memoria locala.
- Foloseste progresul anterior pentru a adapta explicatiile, fara a folosi
  memoria ca sursa factuala.
- Afiseaza un dashboard de progres cu intrebari, cursuri studiate, streak,
  subiecte slabe, quiz average, documente recente si recomandari smart.
- Afiseaza un panou de diagnostics cu path-urile active.

## Structura

```text
ai-facultate-code/
  app.py
  requirements.txt
  install.ps1
  run_app.ps1
  START_AI_STUDY_ASSISTANT.bat
  start_server.bat
  client_app/
    launcher.py
    assets/
      copilot_facultate.ico
  build_client.bat
  INSTALL_CLIENT.md
  api_server.py
  user_accounts.py
  manage_users.py
  README.md
  study_memory.py
  documents/
  storage/
    chroma/
    memory/
    auth/
    users/<username>/
      documents/
      memory/
```

## Instalare pe orice PC Windows

1. Instaleaza Python 3.12 sau 3.11. Nu folosi Python 3.14 pentru acest proiect.
2. Instaleaza Ollama.
3. Descarca modelele in Ollama:

```powershell
ollama pull qwen3:8b
ollama pull nomic-embed-text
```

4. Deschide PowerShell in folderul proiectului.
5. Ruleaza:

```powershell
.\install.ps1
```

Scriptul creeaza `.venv` local si instaleaza dependintele.

Daca ai mai multe versiuni Python instalate, `install.ps1` alege automat Python 3.12 sau 3.11. Optional, poti indica explicit executabilul:

```powershell
$env:PYTHON_EXE = "C:\Path\To\Python312\python.exe"
.\install.ps1
```

## Pornire

Varianta simpla:

```text
Dublu click pe START_AI_STUDY_ASSISTANT.bat
```

Varianta PowerShell:

```powershell
.\run_app.ps1
```

Scriptul porneste aplicatia din folderul curent al proiectului. Daca portul `8501` este ocupat, foloseste urmatorul port liber pana la `8510`.

## Moduri in tab-ul Intrebari

Tab-ul `Intrebari` este interfata principala de chat. Intrebarile si raspunsurile
raman vizibile ca mesaje succesive, iar raspunsul este afisat progresiv in timpul
generarii. Inputul de chat ramane jos, ca in aplicatiile moderne de asistenti AI.

In partea de sus a sidebarului gasesti:

- `Chat nou` pentru o conversatie separata;
- `Cauta conversatii` pentru cautare in titluri si mesaje;
- lista conversatiilor anterioare, ordonata dupa ultima activitate;
- butonul `×` pentru stergerea unei conversatii.

Titlul este creat automat din prima intrebare. La redeschidere sunt restaurate
mesajele, sursele, modul de raspuns, profilul de viteza si documentele selectate.
Sub fiecare raspuns al asistentului poti deschide sursele si detaliile retrieval.
Ultimul raspuns pastreaza si actiunile `Greu`, `Neclar` si `De repetat`.

Conversatiile sunt salvate exclusiv local in:

```text
storage/memory/study_memory.sqlite3
```

Tabelele `conversations` si `conversation_messages` contin titlurile, timestampurile,
mesajele, sursele si metadatele. Nu sunt trimise catre cloud.

Tab-ul `Intrebari` contine patru moduri:

1. `Intrebare normala` pentru intrebari RAG globale.
2. `Compara cursuri` pentru selectarea si compararea a cel putin doua documente.
3. `Rezumat document` pentru rezumatul unui singur document.
4. `Cauta in document specific` pentru retrieval limitat la documentul ales.

### Moduri de raspuns si rationament

Dropdown-ul `Mod raspuns` din tab-ul `Intrebari` controleaza felul in care
Faculty Copilot foloseste dovezile din cursuri:

- `Auto` este implicit si detecteaza intentia intrebarii.
- `Strict` reda numai fapte explicite, formule si definitii din documente.
- `Analiza` permite comparatie, sinteza, inferenta prudenta si clasamente
  argumentate. Raspunsul separa faptele, analiza si concluzia.
- `Profesor` explica pas cu pas, cu analogii si exemple pedagogice, pastrand
  citarile documentelor.
- `Strategie de invatare` combina continutul cursurilor cu memoria locala:
  subiecte slabe, rezultate la quiz, documente neglijate si planul de examen.

In modul `Auto`, expresii precum `defineste` si `formula` aleg `Strict`,
`compara` si `care e mai greu` aleg `Analiza`, `explica-mi` si `de ce` aleg
`Profesor`, iar `cum invat` si `ce repet` aleg `Strategie de invatare`.

Controlul separat `Viteza si precizie` din sidebar pastreaza profilurile
`Fast`, `Balanced` si `Accurate`. Stilul de rationament si cantitatea de context
sunt doua setari independente.

### Rutare automată a cunoștințelor și modelelor

Rutarea automată este activă implicit. Utilizatorul nu trebuie să aleagă manual
între documente și cunoștințe generale:

- o întrebare despre cursuri folosește RAG și profilul `RAG model`;
- o întrebare generală sare peste ChromaDB și folosește `General knowledge model`;
- o întrebare mixtă folosește RAG pentru curs, cunoștințele modelului pentru
  partea externă și `Reasoning/Professor model` pentru sinteza finală;
- `Fast` are prioritate și folosește `Fast model`;
- `Accurate` preferă modelul de reasoning configurat.

În `Setări -> Model routing` pot fi configurate separat profilele RAG, general,
reasoning și fast. Modelele instalate sunt detectate automat. Dacă unul lipsește,
aplicația avertizează și alege un model instalat ca fallback. Pentru RTX 3070
8GB, `qwen3:8b` este alegerea rapidă, `qwen3:14b` oferă reasoning mai bun dar
este mai lent, iar `gemma3:12b` este o opțiune bună pentru conversație generală
dacă este instalat. Acestea sunt recomandări, nu valori obligatorii.

Intentiile detectate includ: intrebare de curs, cautare in document, comparatie,
planificare, flashcards, quiz, memorie, cunostinte generale si intrebare mixta.
Pentru o intrebare mixta, raspunsul separa `Din documentele tale`, `Cunostinte
generale` si `Legatura / concluzia`. Citarile document/pagina apar numai in
partea sustinuta de RAG.

Fiecare raspuns afiseaza ruta, intentia si un scor de incredere. Daca relevanta
documentelor este incerta, modul implicit prefera un raspuns hibrid in locul
unui refuz. Informatiile generale nu primesc citari de curs inventate.

Taburile principale sunt:

```text
Intrebari
Flashcards
Quiz
Progres
Plan sesiune
Setari
```

Nu exista un mod interactiv de study session. `Plan sesiune` este pentru
planificarea examenelor/sesiunii dupa documentele indexate si memoria locala.

## Viteza raspunsurilor

In sidebar, controlul `Viteza si precizie` ofera:

- `Fast`: 5 fragmente, context mai scurt, raspuns concis si timeout de 180 secunde.
- `Balanced`: profilul implicit, 9 fragmente si un echilibru intre viteza si detalii.
- `Accurate`: 14 fragmente, context extins, raspuns mai riguros si citari mai stricte.

Retrieval-ul semantic este pastrat in cache pentru intrebarile repetate. Cache-ul
se invalideaza automat cand este creat un index nou. Fragmentele aproape identice
sunt eliminate inainte de trimiterea catre model, iar lista de surse contine
numai fragmentele folosite efectiv in context.

Raspunsurile din tab-ul `Intrebari` sunt afisate progresiv in timpul generarii.
Flashcards si quizurile asteapta raspunsul complet deoarece modelul trebuie sa
produca JSON valid.

Daca Ollama depaseste timpul profilului selectat, aplicatia afiseaza un mesaj
clar. In acest caz foloseste `Fast`, formuleaza o intrebare mai specifica sau
selecteaza un document anume.

### Compararea mai multor cursuri

Modul `Compara cursuri` foloseste un pipeline in doua etape:

1. Recupereaza numai fragmentele cele mai relevante din fiecare curs.
2. Genereaza si memoreaza in cache un rezumat separat pentru fiecare curs.
3. Compara rezumatele, nu toate fragmentele brute simultan.

Limita implicita de fragmente per curs depinde de profil:

- `Fast`: 2 fragmente per curs;
- `Balanced`: 4 fragmente per curs;
- `Accurate`: 8 fragmente per curs.

In interfata poti modifica `Max. fragmente per curs` si `Lungime maxima raspuns
(tokeni)`. Toate apelurile Ollama au cel putin 180 de secunde disponibile.
Comparatia finala este afisata progresiv. Daca un rezumat sau comparatia finala
depaseste timpul disponibil, aplicatia pastreaza rezumatele deja obtinute si
returneaza rezultate partiale in loc sa piarda intreaga comparatie.

## Plan sesiune

Tabul `Plan sesiune` genereaza un plan realist zi cu zi dupa cursurile indexate.
Completezi:

- materia;
- documentele/cursurile incluse;
- cate zile ai pana la examen;
- cate ore poti studia pe zi;
- optional, calcul automat pentru orele necesare pe zi;
- nivelul de dificultate: `low`, `medium` sau `high`;
- daca vrei zile de recapitulare;
- daca vrei zile de quiz/flashcards;
- optional, data examenului.

Aplicatia estimeaza workload-ul local folosind numarul de documente, pagini,
chunk-uri, dificultatea aleasa si subiectele slabe salvate in memorie. Planul
include pentru fiecare zi:

- documentele, paginile sau partile de parcurs;
- orele estimate;
- timp de recapitulare;
- timp de quiz/flashcards, daca este activat;
- topicuri prioritare;
- subiecte slabe de repetat.

Daca timpul disponibil nu pare suficient, aplicatia afiseaza un avertisment
clar. Planul este salvat local in SQLite si apare apoi in sectiunea
`Planuri salvate`.

Planul incepe implicit cu data de azi. Daca setezi data examenului, ultima zi
de studiu este ziua dinaintea examenului, iar numarul de zile disponibile este
calculat automat intre azi si examen. Modul automat de ore imparte workload-ul
total pe zilele disponibile si afiseaza `Ore recomandate pe zi`. Daca rezultatul
trece de 4h/zi, 6h/zi sau 8h/zi, aplicatia marcheaza planul ca greu, foarte greu
sau nerealist.

Butonul `Genereaza orar .ics` creeaza local un fisier calendar `.ics`. Nu exista
integrare cu Google Calendar sau cloud. Fisierul poate fi importat manual in
aplicatia ta de calendar, daca vrei.

## Access from phone/laptop

PC-ul desktop este serverul. Ollama, modelele Qwen, embeddings, ChromaDB,
memoria SQLite si inferenta pe RTX 3070 ruleaza numai pe desktop.

Telefonul sau laptopul afiseaza doar interfata Streamlit in browser. Nu instala
si nu rula Ollama sau modelele pe telefon/laptop.

În modul remote, selectorul de fișiere aparține browserului de pe laptop sau
telefon. Fișierele sunt încărcate prin HTTP pe desktop, salvate în folderul
privat al utilizatorului și apoi indexate acolo. Nu se deschide niciun dialog de
fișiere pe desktopul server. Dialogul Windows al serverului este disponibil
numai când aplicația este pornită local prin `run_app.ps1`.

1. Porneste Ollama pe desktop.
2. Pe desktop, da dublu click pe:

```text
start_server.bat
```

3. Aplicatia porneste pe `0.0.0.0`, portul fix `8501`.
4. In aplicatie, sectiunea `Acces server` afiseaza:

```text
Local: http://localhost:8501
LAN: http://ADRESA_PC:8501
Tailscale: http://ADRESA_TAILSCALE:8501
```

5. Pentru un telefon/laptop din aceeasi retea Wi-Fi, deschide URL-ul `LAN`.
6. Pentru acces din afara casei, instalează Tailscale pe desktop și pe client.
   Din consola Tailscale, invită prietenul în tailnet sau folosește funcția
   `Share` pentru dispozitivul server, apoi oferă-i URL-ul Tailscale afișat.
7. Cu setarea implicită nu apare ecranul de login: toți clienții folosesc
   workspace-ul comun `default_user`. Activează autentificarea numai când ai
   nevoie de conturi separate.

La prima pornire, Windows Firewall poate cere permisiune. Permite accesul numai
pentru retele private de incredere.

**AVERTISMENT: Nu expune portul 8501 direct pe internetul public. Nu configura
port forwarding in router. Pentru acces remote foloseste Tailscale.**

### Autentificare opțională

Autentificarea este dezactivată implicit pentru testare locală, LAN și
Tailscale. `start_server.bat` pornește serverul cu:

```text
FACULTY_COPILOT_AUTH_ENABLED=0
FACULTY_COPILOT_DEFAULT_USER=default_user
```

În acest mod nu se cere utilizator sau parolă. Streamlit și FastAPI folosesc
automat `default_user`, iar documentele, memoria și colecția sa rămân în
arhitectura de workspace per utilizator. Toate dispozitivele conectate văd
același spațiu, deci folosește acest mod numai într-o rețea privată de
încredere.

Pentru a reactiva login-ul și izolarea multi-user fără alte schimbări de cod:

```powershell
$env:FACULTY_COPILOT_AUTH_ENABLED = "1"
.\start_server.bat
```

Cu autentificarea activă, creează conturile cu `manage_users.py`; fiecare cont
primește propriile documente, memorie și colecție Chroma. Variabila opțională
`FACULTY_COPILOT_DEFAULT_USER` schimbă numele workspace-ului comun folosit doar
când autentificarea este oprită.

## Arhitectura client-server

Pentru folosire pe laptopuri Windows, proiectul are acum o separare clara:

Serverul desktop ruleaza:

- Ollama;
- modelele locale;
- ChromaDB;
- SQLite memory;
- FastAPI;
- Streamlit ca interfata unica.

Clientul ruleaza doar:

- un launcher Windows WebView2;
- o fereastra nativa fara bara de adresa;
- interfata Streamlit incarcata de pe server.

Clientul nu ruleaza Ollama, nu descarca modele AI si nu creeaza ChromaDB.
Clientul nu recreeaza interfata in Tkinter si nu dubleaza codul UI.

### Pornire server AI

Pe desktop, porneste Ollama si apoi ruleaza:

```text
start_server.bat
```

Implicit, serverul porneste:

```text
Streamlit UI: http://localhost:8501
FastAPI:      http://localhost:8000
```

Pentru LAN sau Tailscale, launcherul Windows foloseste URL-ul Streamlit:

```text
http://ADRESA_LAN:8501
http://ADRESA_TAILSCALE:8501
```

Endpoint-uri server:

```text
POST   /auth/login
POST   /documents/upload
POST   /documents/index
GET    /documents
POST   /ask
POST   /compare
POST   /quiz
POST   /flashcards
POST   /session-plan
GET    /progress
GET    /health
GET    /routing/debug
GET    /queue
GET    /requests/{request_id}
DELETE /requests/{request_id}
```

Documentatia API este disponibila pe server la:

```text
http://localhost:8000/docs
```

### Client desktop Windows .exe

Pentru un laptop care trebuie sa instaleze doar o aplicatie usoara, foloseste
launcherul desktop din `client_app/`.

Pe desktopul/serverul unde este proiectul, construieste executabilul:

```text
build_client.bat
```

Output:

```text
dist\Copilot Facultate.exe
```

Copiaza acest `.exe` pe laptop. La prima pornire, launcherul intreaba pentru:

- URL-ul serverului desktop, de exemplu `http://192.168.1.201:8000`.

Launcherul are butoanele `Test connection`, `Save` si `Open app`. Memoreaza
URL-ul local in `%APPDATA%\Copilot Facultate\config.json` si apoi deschide
direct acelasi Streamlit UI pe care il vezi pe desktop. Daca introduci portul
API `8000`, launcherul testeaza `/health` si deschide automat Streamlit pe
portul `8501`. Titlul ferestrei este `Copilot Facultate`, fara bara de adresa de
browser.

Pentru schimbarea ulterioara a serverului foloseste meniul:

```text
Copilot -> Setari server
```

Pasii completi pentru utilizatori incepatori sunt in:

```text
INSTALL_CLIENT.md
```

Flux recomandat:

1. Porneste serverul pe desktop cu `start_server.bat`.
2. Instaleaza/deschide clientul pe laptop.
3. Introdu URL-ul serverului, de exemplu `http://100.x.y.z:8000`.
4. Apasa `Test connection`, `Save`, apoi `Open app`.
5. Foloseste aceeasi interfata Streamlit, in fereastra nativa.

#### Instalarea unui utilizator nou (auth ON)

Utilizatorul nou nu are nevoie de Python, Ollama, modele sau ChromaDB pe laptop:

1. Administratorul creează contul pe desktop, din folderul proiectului:

```powershell
.\.venv\Scripts\python.exe manage_users.py ana --password "o-parola-lunga"
```

Comanda afișează și un token API. Trimite parola sau tokenul printr-un canal
privat; nu le adăuga în Git și nu le publica.

2. Administratorul pornește `start_server.bat` pe desktopul cu RTX 3070.
3. Pe laptop se instalează Tailscale și se acceptă invitația/share-ul pentru
   desktopul server.
4. Se descarcă sau se copiază numai `Copilot Facultate.exe` din release-ul
   Windows. Pe Windows 11, WebView2 este deja inclus in mod normal.
5. La prima pornire se introduce `http://ADRESA_TAILSCALE:8000`.
6. Se apasă `Test connection`, `Save`, apoi `Open app`.
7. În fereastra Streamlit se introduc utilizatorul și parola/tokenul. Acest pas
   nu apare când `FACULTY_COPILOT_AUTH_ENABLED=0`.
8. Cursurile se aleg cu uploaderul din browserul laptopului.

Toți utilizatorii folosesc același GPU și aceeași coadă, dar au directoare de
documente, colecții Chroma și baze SQLite de memorie separate.

### Coada multi-user si GPU

FastAPI si Streamlit folosesc aceeasi coada persistenta din SQLite. Retrieval-ul
ChromaDB poate rula pentru mai multi utilizatori, dar generarea Ollama ocupa un
slot GPU. Limita implicita este `1`, recomandata pentru RTX 3070 8GB.

Limita poate fi schimbata in `Setari -> Concurenta server AI`, intre `1` si `4`.
La incarcare mare, clientul ramane activ si afiseaza:

```text
AI-ul este ocupat. Ești în coadă: poziția X.
```

Diagnosticul arata utilizatorii activi, cererile in asteptare, cererile care
ruleaza si timpul mediu de raspuns. Daca serverul este repornit, cererile ramase
orfane sunt marcate ca esuate in loc sa blocheze coada.

### HTTPS si Tailscale

Cel mai simplu mod sigur pentru acces remote este Tailscale. Nu folosi port
forwarding public.

Pentru prieteni de încredere, recomandarea este `Tailscale Share`: serverul
rămâne într-o rețea privată și nu primește un port public. Pentru o eventuală
aplicație publică sunt deja pregătite autentificarea cu token, rate limiting și
separarea per-utilizator, dar înainte de publicare mai sunt obligatorii un
reverse proxy HTTPS, rotația secretelor, audit și politici de backup. **Nu
expune nici portul 8000, nici 8501 direct pe internet, chiar dacă autentificarea
este activă.**

HTTPS este suportat daca ai certificat si cheie locala. Pe server setezi:

```powershell
$env:FACULTY_COPILOT_SSL_CERTFILE = "C:\cale\cert.pem"
$env:FACULTY_COPILOT_SSL_KEYFILE = "C:\cale\key.pem"
.\start_server.bat
```

Launcherul va folosi apoi o adresa de forma:

```text
https://ADRESA_TAILSCALE:8501
```

Aceeasi arhitectura poate fi folosita mai tarziu pentru macOS, Linux, Android
si iPhone: clientii trebuie doar sa afiseze Streamlit-ul serverului sau sa
apeleze API-ul FastAPI.

## Documente si baza de date

Folderul implicit pentru documente este:

```text
documents/
```

Acesta este folosit numai în modul local. În modul remote fiecare cont are:

```text
storage/users/<username>/documents/
storage/users/<username>/memory/study_memory.sqlite3
storage/users/<username>/active_collection.txt
```

Baza ChromaDB este salvata local in:

```text
storage/chroma/
```

Fișierele Chroma sunt administrate de server, dar fiecare utilizator are o
colecție/namespace separat. Documentele și memoria unui cont nu intră în
retrieval-ul altui cont.

Memoria de studiu este salvata local in:

```text
storage/memory/study_memory.sqlite3
```

In aceeasi baza SQLite sunt salvate si:

- metadatele academice editabile pentru documente: an, materie, curs;
- planurile de sesiune generate;
- zilele planificate si documentele incluse;
- preferintele locale ale aplicatiei.

Fisierul colectiei active este:

```text
storage/active_collection.txt
```

Toate aceste path-uri sunt relative la folderul proiectului.

## Memorie de studiu

Aplicatia salveaza:

- intrebarile si momentul in care au fost puse;
- documentul selectat si documentele recuperate prin RAG;
- subiectul detectat, un rezumat al raspunsului si sursele;
- marcajele `greu`, `neclar` si `de repetat`;
- fiecare intrebare de quiz, raspunsul ales, raspunsul corect si scorul;
- sesiunile recente si documentele studiate.
- metadatele academice `An -> Materie -> Curs` pentru fiecare document;
- planurile de sesiune generate si zilele aferente.
- modelul Ollama selectat, ca preferinta locala.

Sub un raspuns sunt disponibile actiunile:

- `Marcheaza ca greu`;
- `Marcheaza ca neclar`;
- `Adauga la repetat`.

In sidebar, sectiunea `Memorie de studiu` arata totalurile si ofera:

- `Arata subiectele slabe`;
- `Genereaza recapitulare din subiectele slabe`.

Tab-ul `Progres` contine totalul intrebarilor, cursurile studiate, subiectele
slabe, media quizurilor, streak-ul de studiu, ultimele documente studiate,
intrebarile recente, rezultatele quizurilor, planurile recente si recomandari
smart pentru urmatoarea recapitulare.

Tab-ul `Setari` contine editorul de metadate academice. Pentru fiecare document
poti modifica anul, materia si cursul. Schimbarile sunt salvate local in SQLite
si sunt folosite apoi in `Documente indexate`, `Progres` si `Plan sesiune`.

## Confidentialitate

Memoria ramane pe PC in `storage/memory/`. Aplicatia nu o incarca intr-un
serviciu cloud si nu o foloseste pentru fine-tuning. Ollama continua sa ruleze
local, iar ChromaDB, SQLite si fisierele `.ics` generate sunt locale.

Folderul `storage/memory/` este ignorat de Git. Un commit nu va include istoricul
personal, subiectele slabe sau rezultatele quizurilor.

Pentru backup personal, copiaza separat folderul `storage/memory/`. Pentru a
reseta memoria, inchide aplicatia si sterge acest folder; baza va fi recreata
automat la urmatoarea pornire.

## Verificare in aplicatie

In sidebar, sectiunea `Diagnostics` arata:

- Current project root
- Current storage folder
- Current documents folder
- Current database path
- Current memory database
- Active collection

In partea de sus a aplicatiei apare si `Proiect activ`, ca sa vezi exact din ce folder ruleaza.

In modul server sunt afisate si URL-urile local, LAN si Tailscale, daca
Tailscale este instalat si conectat.

## API FastAPI

Fisierul `api_server.py` este backend-ul pentru arhitectura client-server.
Streamlit `app.py` ramane singura interfata de studiu, iar launcherul din
`client_app/launcher.py` o afiseaza intr-o fereastra WebView2 pe laptop.

Endpoint-uri:

```text
POST /auth/login
POST /documents/upload
POST /documents/index
POST /ask
POST /compare
POST /quiz
POST /flashcards
POST /session-plan
GET  /documents
GET  /health
GET  /progress
GET  /queue
GET  /routing/debug
GET  /requests/{request_id}
DELETE /requests/{request_id}
```

Endpoint-urile `POST` accepta optional:

```json
{
  "response_mode": "Balanced",
  "answer_mode": "Auto",
  "knowledge_mode": "Hybrid (recommended)",
  "auto_routing": true,
  "request_id": "client-uuid-generat-local"
}
```

Valorile permise sunt `Fast`, `Balanced` si `Accurate`.
Pentru `answer_mode`, valorile permise sunt `Auto`, `Strict`, `Analiză`,
`Profesor` si `Strategie de învățare`, exact ca in interfata.
Cu `auto_routing: true` (implicit), serverul decide automat ruta și ignoră
alegerea manuală `knowledge_mode`. Setează `auto_routing: false` numai pentru
testare sau pentru un client avansat.

Cu `FACULTY_COPILOT_AUTH_ENABLED=0` (implicit), endpoint-urile folosesc automat
`default_user` și nu cer headere de autentificare. Cu
`FACULTY_COPILOT_AUTH_ENABLED=1`, toate endpoint-urile, cu excepția `/health` și
`/auth/login`, cer autentificare:

```http
Authorization: Bearer TOKENUL_UTILIZATORULUI
```

Alternativ se poate folosi headerul `X-API-Key`. Uploadul folosește
`multipart/form-data`, iar `/documents/index` indexează numai fișierele din
spațiul utilizatorului selectat de modul de autentificare.

`request_id` este optional. Un client care vrea polling sau anulare il genereaza
inainte de `POST`, apoi poate apela:

```text
GET    /requests/client-uuid-generat-local
DELETE /requests/client-uuid-generat-local
```

Statusurile sunt `queued`, `running`, `completed` si `failed`. Raspunsul final
al endpointului include acelasi `request_id`. `GET /queue` returneaza sumarul
multi-user si limita curenta de generari simultane.

Pornire locala pentru dezvoltare:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api_server:app --host 0.0.0.0 --port 8000
```

Documentatia interactiva FastAPI este disponibila la:

```text
http://localhost:8000/docs
```

API-ul foloseste acelasi Ollama, aceeasi baza ChromaDB si aceeasi memorie locala
de pe desktop. Clientii trimit doar JSON si primesc JSON. Pentru testare de pe
alt dispozitiv, foloseste numai o retea privata de incredere sau Tailscale. Nu
expune nici portul API direct pe internetul public.

## Exemple

Intrebare despre un document anume:

```text
despre ce este cursul 1
rezumat cursul 3
ce contine cursul 5
```

Intrebari globale de continut:

```text
ce este energia interna
explica difractia
```

Exemple pentru noile moduri de rationament:

```text
Care curs pare cel mai greu și de ce?
Compară Cursul 1 cu Cursul 12.
Ce ar trebui să învăț prima dată pentru examen?
Explică efectul tunel ca unui student de anul I.
```

Intrebari despre inventar:

```text
ce cursuri am indexat?
ce documente sunt indexate?
```

## Mutare pe alt PC

Copiaza tot folderul proiectului pe noul PC, apoi ruleaza:

```powershell
.\install.ps1
.\run_app.ps1
```

Nu trebuie modificat niciun path in cod.

Daca vrei sa muti si progresul personal, copiaza si `storage/memory/`. Daca nu,
aplicatia va crea automat o memorie noua pe noul PC.
