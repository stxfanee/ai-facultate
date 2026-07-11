# Co-pilot Facultate

Aplicatie locala pentru facultate, construita peste documentele tale indexate.

Co-pilot Facultate extinde asistentul RAG într-un copilot academic local:
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
  desktop_client/
    launcher.py
    assets/
      faculty_copilot.ico
  build_desktop_client.bat
  desktop_app/
    launcher.py
    assets/
      copilot_facultate.ico
  build_copilot_facultate.bat
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

## Agent de studiu autonom și Notebook

Co-pilot Facultate urmărește local cursurile încărcate, activitatea de studiu,
rezultatele și greșelile din quizuri, seturile de flashcarduri, planurile și
datele examenelor. Când există suficiente date, în zona principală de chat apar
observații proactive bazate pe dovezi, de exemplu cursuri nerevizuite, tipare de
greșeli, risc de întârziere sau semnale de pregătire bună. Estimările sunt
etichetate ca atare și nu sunt prezentate drept certitudini.

Pagina `Notebook` păstrează separat:

- sfaturi de la profesor;
- remindere și note personale;
- indicii pentru examen;
- sfaturi și preferințe de studiu.

Notebook-ul este izolat per profil și poate fi folosit automat pentru
personalizarea răspunsurilor. Adăugarea, editarea și ștergerea unei note cer
întotdeauna confirmare explicită în interfață; aceeași regulă este impusă și în
stratul de stocare.

## Workspaces

Fiecare profil poate crea oricâte workspace-uri dorește, de exemplu
`Biochimie`, `Biofizică`, `Genetică`, `Vacation`, `Cars` sau `Programming`.
Schimbarea workspace-ului schimbă simultan:

- conversațiile și contextul lor;
- directorul documentelor și namespace-ul Chroma;
- memoria, progresul și sesiunile;
- quizurile și seturile de flashcarduri;
- Notebook-ul, preferințele și planurile de examen.

Workspace-ul `General` folosește exact directoarele existente ale profilului,
deci migrarea nu mută și nu șterge automat date. Workspace-urile noi sunt
stocate sub `storage/users/<profil>/workspaces/<workspace>/`.

Un chat poate fi mutat din `Opțiuni chat`. Istoricul și routing-ul sunt mutate,
dar fișierele atașate rămân în workspace-ul sursă pentru a evita copierea sau
reindexarea implicită a datelor. Pentru API, trimite headerul
`X-Workspace: biochimie`; fără header este folosit `General`.

## Viewer PDF integrat

Citările PDF au acțiunea `Deschide în PDF`. Aceasta activează split view
`Chat | PDF` și deschide documentul la pagina citată. Viewerul oferă:

- pagina precedentă/următoare și număr de pagină;
- citarea precedentă/următoare din conversație;
- zoom între 50% și 200%;
- căutare în stratul text al întregului PDF;
- miniaturi pentru paginile din jurul paginii active;
- evidențierea paragrafului recuperat pentru citare;
- preview direct din lista documentelor.

PDF-urile cu text OCR existent sunt căutabile automat. Pentru pagini scanate
fără strat text, aplicația încearcă OCR local prin PyMuPDF și Tesseract. Instalează
Tesseract pe desktop și limbile `ron`/`eng` pentru acest fallback; dacă executabilul
nu este disponibil, navigarea și preview-ul PDF continuă să funcționeze, dar pagina
scanată nu va fi căutabilă. PDF-ul este acceptat numai din directorul workspace-ului
curent, astfel încât viewerul nu poate deschide fișierele altui workspace/profil.

## Explain Why

Fiecare răspuns din chat are panoul restrâns `🧠 Explain why`. Panoul explică
sursa cunoștințelor, documentele și paginile folosite, motivul selecției,
rutarea, modelul, încrederea, informațiile lipsă și un rezumat scurt al surselor.
Citările PDF din panou deschid direct viewerul integrat la pagina respectivă.

`Developer Mode` se activează explicit din sidebar și adaugă numai metadate
tehnice aprobate: intenție, rută, documente, scoruri, fragmente recuperate,
model și timpii pentru retrieval/inference/total. Panoul nu solicită și nu
afișează chain-of-thought, prompturi ascunse, reasoning tokens, deliberări
interne sau system prompts.

Tabelele `conversations` si `conversation_messages` contin titlurile, timestampurile,
mesajele, sursele si metadatele. Nu sunt trimise catre cloud.

Tab-ul `Intrebari` contine patru moduri:

1. `Intrebare normala` pentru intrebari RAG globale.
2. `Compara cursuri` pentru selectarea si compararea a cel putin doua documente.
3. `Rezumat document` pentru rezumatul unui singur document.
4. `Cauta in document specific` pentru retrieval limitat la documentul ales.

### Moduri de raspuns si rationament

Dropdown-ul `Mod raspuns` din tab-ul `Intrebari` controleaza felul in care
Co-pilot Facultate folosește dovezile din cursuri:

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

Controlul separat `Model selection` din sidebar păstrează alegerea modelului
independentă de stilul de raționament și de knowledge mode.

### Profile optimizate pentru RTX 3070 8GB

#### Rutare inteligentă

Controlul `Model selection` este separat de profilul de rutare. Implicit este
`Auto recommended`, adica aplicatia decide modelul pentru fiecare intrebare. Daca
alegi manual `qwen3:8b`, `qwen3:14b` sau orice alt model Ollama instalat, acel
model este folosit pentru raspunsuri pana cand revii la `Auto recommended`.
Alegerea este salvata per profil/utilizator.

Controlul `Auto routing profile` inlocuieste vechiul `Model mode` pentru
profilul de viteza/context. Ofera `Auto`, `Fast`, `Balanced` si `Accurate`.
Pe RTX 3070 8GB, 14B poate face spill în RAM și poate răspunde mult mai lent;
modul `Auto` acceptă acest compromis numai când complexitatea îl justifică.
Selectarea `Fast`, `Balanced` sau `Accurate` forțează profilul ales. Modelele,
numărul maxim de fragmente, contextul, output-ul și timeout-ul fiecărui profil
pot fi configurate în Setări. Dacă 14B expiră sau rămâne fără resurse, cererea
este reluată cu modelul Fast și fallback-ul apare în diagnostic.

Profilele controlează modelul, contextul, output-ul, temperatura, `top_p`,
timeout-ul, `keep_alive` și numărul de fragmente RAG:

| Profil | Model recomandat | Context | Output max. | Fragmente | Utilizare |
| --- | --- | ---: | ---: | ---: | --- |
| Fast | `qwen3:8b` quantizat | 4096 | 700 | 4 | întrebări simple și latență mică |
| Balanced | `qwen3:8b` pe RTX 3070 8GB | 6144 | 1200 | 7 | RAG și conversații normale |
| Accurate | `qwen3:14b` | 8192 | 2000 | 10 | reasoning dificil, posibil mai lent |

Estimarea VRAM folosește dimensiunea și quantizarea raportate de Ollama plus un
buget pentru KV cache. La peste aproximativ 90% din VRAM aplicația avertizează
că modelul poate muta layere în RAM/CPU. Modul `Auto` permite acest compromis
numai pentru cererile evaluate drept complexe.

În `Setări -> Profile RTX 3070 8GB` pot fi schimbate modelul preferat, context
size, max output tokens, max retrieved chunks și timeout-ul fiecărui profil. La timeout
sau eroare de memorie, generarea reîncearcă automat cu modelul Fast instalat.

Pagina `Benchmark` testează modelele Ollama instalate și raportează timpul de
răspuns, tokeni/secundă, lungimea răspunsului, rata timeout-urilor și VRAM-ul
runtime raportat de Ollama atunci când este disponibil. Modelele sunt testate
secvențial pentru a nu supraîncărca RTX 3070.

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
7. Cu setarea implicită nu apare ecran de parolă. La prima vizită aplicația
   întreabă `Cine folosește aplicația?`, iar fiecare persoană își creează sau
   selectează un profil local fără parolă.

La prima pornire, Windows Firewall poate cere permisiune. Permite accesul numai
pentru retele private de incredere.

**AVERTISMENT: Nu expune portul 8501 direct pe internetul public. Nu configura
port forwarding in router. Pentru acces remote folosește Tailscale, Cloudflare
Tunnel sau Tailscale Funnel.**

### Autentificare opțională

Autentificarea este dezactivată implicit pentru testare locală, LAN și
Tailscale. `start_server.bat` pornește serverul cu:

```text
FACULTY_COPILOT_AUTH_ENABLED=0
FACULTY_COPILOT_DEFAULT_USER=default_user
```

În acest mod nu se cere parolă. Streamlit afișează un selector de profil
(`Cine folosește aplicația?`) și fiecare profil primește propriul workspace:
documente, memorie SQLite, conversații, progres, flashcards, quiz-uri, planuri
de sesiune și colecții Chroma separate. FastAPI poate folosi headerul
`X-User-Profile` pentru același comportament; fără header păstrează fallback-ul
compatibil `default_user`.

Profilurile fără parolă sunt pentru testare locală, LAN și Tailscale cu oameni
de încredere. Nu sunt o barieră de securitate: oricine are acces la aplicație
poate selecta sau crea un profil cât timp autentificarea este OFF.

Pentru a reactiva login-ul și izolarea multi-user fără alte schimbări de cod:

```powershell
$env:FACULTY_COPILOT_AUTH_ENABLED = "1"
.\start_server.bat
```

Cu autentificarea activă, creează conturile cu `manage_users.py`; fiecare cont
primește propriile documente, memorie și colecție Chroma. Variabila opțională
`FACULTY_COPILOT_DEFAULT_USER` schimbă numele workspace-ului comun folosit doar
când autentificarea este oprită.

### Profiluri și management documente

În modul auth OFF, sidebarul afișează `Utilizator curent` cu:

- schimbare profil;
- creare profil nou;
- ștergere profil curent cu confirmare.

Fiecare profil vede numai documentele proprii. Documentele încărcate recent
devin active pentru profilul curent, iar selecția din `Întrebare normală`
restricționează retrieval-ul la documentele selectate. În lista de documente
indexate poți:

- redenumi un document;
- șterge un document din folder, ChromaDB și metadata;
- re-indexa biblioteca profilului curent;
- șterge toate documentele profilului curent cu confirmare.

## Deployment modes

Desktopul rămâne singurul server AI în toate modurile. Ollama, modelele,
ChromaDB, documentele și SQLite rulează numai pe desktop; browserul prietenului
primește doar interfața și nu descarcă modele.

Modul se setează înainte de `start_server.bat` prin
`FACULTY_COPILOT_DEPLOYMENT_MODE`:

| Mod | Utilizare | Expunere |
| --- | --- | --- |
| `Local` | numai desktop | `localhost` |
| `LAN` | dispozitive din aceeași rețea | IP privat, porturile 8501/8000 |
| `Tailscale` | dispozitive autorizate în tailnet | IP Tailscale, fără Internet public |
| `Public Internet` | URL HTTPS pentru orice browser | numai prin tunnel/reverse proxy |

Pagina `Server Status` afișează modul activ, URL-urile Local/LAN/Tailscale/Public,
starea HTTPS, sesiunile observate recent, coada, generările active și utilizarea
GPU raportată de `nvidia-smi`. URL-ul public este doar configurat și afișat de
aplicație; pornirea unui tunnel rămâne o acțiune explicită a administratorului.

### Local mode

Pentru utilizare numai pe desktop rulează `run_app.ps1`. Serviciile nu trebuie
publicate, iar URL-ul este `http://localhost:8501`.

### LAN mode

`start_server.bat` folosește implicit modul `LAN` și ascultă pe `0.0.0.0` pentru
rețeaua locală. Pagina de status detectează adresa LAN. Permite porturile în
Windows Firewall numai pe profilul Private; nu crea reguli de port forwarding
în router.

### Tailscale mode

Pentru acces privat din afara casei, instalează Tailscale pe desktop și pe
clienți, apoi setează:

```powershell
$env:FACULTY_COPILOT_DEPLOYMENT_MODE = "Tailscale"
.\start_server.bat
```

Distribuie URL-ul Tailscale doar persoanelor autorizate în tailnet. Acest mod nu
este public; pentru persoane fără Tailscale folosește Cloudflare Tunnel sau
Tailscale Funnel.

### Public Internet mode

Nu expune direct porturile 8000/8501 și nu configura port forwarding. Modul
public presupune un endpoint HTTPS care inițiază conexiuni outbound de pe
desktop către Cloudflare Tunnel ori Tailscale Funnel. Pentru prieteni este
suficient URL-ul public Streamlit; URL-ul FastAPI este opțional.

Exemplu de configurare înainte de pornire:

```powershell
$env:FACULTY_COPILOT_DEPLOYMENT_MODE = "Public Internet"
$env:FACULTY_COPILOT_PUBLIC_URL = "https://study.example.com"
$env:FACULTY_COPILOT_PUBLIC_API_URL = "https://api.study.example.com"
$env:FACULTY_COPILOT_ALLOWED_ORIGINS = "https://study.example.com"
$env:FACULTY_COPILOT_ALLOWED_HOSTS = "study.example.com,api.study.example.com,localhost,127.0.0.1"
.\start_server.bat
```

URL-urile publice sunt acceptate numai cu schema `https://` și la rădăcina unui
hostname (fără subpath). Reverse proxy-ul
trebuie să păstreze `Host`, `X-Forwarded-For`, `X-Forwarded-Proto` și upgrade-ul
WebSocket. Uvicorn are proxy headers activate doar pentru proxy-urile declarate
în `FACULTY_COPILOT_TRUSTED_PROXY_IPS` (implicit loopback).

Protecțiile de origine rămân active chiar dacă autentificarea este OFF:

- maximum 10 fișiere și 100 MB/fișier, maximum 250 MB/cerere de upload;
- rate limit implicit de 60 cereri/minut pentru fiecare IP;
- maximum 32 cereri FastAPI simultane;
- maximum 20 acțiuni AI Streamlit/minut/client și 8 acțiuni UI simultane;
- timeout API de 600 secunde și timeout-uri separate pentru generare;
- coadă persistentă și limită separată pentru sloturile GPU.

Valorile se schimbă prin `FACULTY_COPILOT_MAX_UPLOAD_FILES`,
`FACULTY_COPILOT_MAX_UPLOAD_MB`, `FACULTY_COPILOT_MAX_TOTAL_UPLOAD_MB`,
`FACULTY_COPILOT_IP_RATE_LIMIT`, `FACULTY_COPILOT_MAX_CONCURRENT_REQUESTS` și
`FACULTY_COPILOT_API_TIMEOUT_SECONDS`. Pentru UI există separat
`FACULTY_COPILOT_STREAMLIT_ACTION_RATE_LIMIT` și
`FACULTY_COPILOT_MAX_CONCURRENT_UI_ACTIONS`.

Cu auth OFF, toate persoanele care cunosc URL-ul pot selecta sau crea profiluri
fără parolă. Profilurile izolează datele între utilizatori, dar nu opresc pe
cineva rău intenționat să intre pe un profil existent. Rate limiting-ul nu
înlocuiește controlul accesului. Pentru distribuire dincolo de un grup de
încredere, setează `FACULTY_COPILOT_AUTH_ENABLED=1`.

### Quick public access with Cloudflare Tunnel

Cloudflare Tunnel este metoda recomandată pentru a trimite prietenilor un link
HTTPS fără Tailscale și fără port forwarding. Varianta rapidă publică numai
Streamlit (`localhost:8501`); FastAPI rămâne local pe `8000`, deoarece browserul
nu are nevoie să îl acceseze direct.

1. Instalează `cloudflared` pe desktop din PowerShell:

   ```powershell
   winget install --id Cloudflare.cloudflared
   ```

   Alternativ, descarcă executabilul din pagina oficială
   [Cloudflare downloads](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/).
   După instalare, redeschide terminalul pentru actualizarea `PATH`.

2. Rulează din folderul proiectului:

   ```text
   START_CLOUDFLARE_TUNNEL.bat
   ```

3. Launcherul verifică `cloudflared`, creează un Quick Tunnel outbound către
   `http://127.0.0.1:8501`, pornește aplicația dacă este necesar și afișează un
   URL de forma:

   ```text
   https://nume-aleator.trycloudflare.com
   ```

4. URL-ul apare automat și în `Server Status -> Public`, cu HTTPS activ. Ține
   fereastra launcherului deschisă; când tunnel-ul se oprește, URL-ul temporar
   expiră și este eliminat din Server Status.

Quick Tunnel nu cere cont sau domeniu, dar URL-ul se schimbă la fiecare pornire
și este destinat testării. Launcherul păstrează autentificarea OFF și setează
explicit rate limiting-ul, limita de upload, concurența, timeout-ul și coada
existente. Oricine cunoaște linkul poate deschide aplicația și poate selecta un
profil fără parolă: distribuie linkul numai persoanelor de încredere.

Pentru un hostname stabil precum `study.example.com`, urmează configurarea de
mai jos pentru un tunnel administrat. Niciuna dintre variante nu necesită
deschiderea porturilor `8501` sau `8000` în router.

### Cloudflare Tunnel setup with a custom domain

Ai nevoie de un domeniu administrat în Cloudflare și de `cloudflared` pe
desktop. În dashboard, mergi la `Networking -> Tunnels`, creează un tunnel și
instalează conectorul Windows folosind comanda afișată de Cloudflare. Adaugă
două rute `Published application`:

```text
study.example.com      -> http://localhost:8501
api.study.example.com  -> http://localhost:8000
```

Cloudflare termină HTTPS și transmite WebSocket-urile Streamlit. În pagina
Cloudflare `Network`, păstrează WebSockets activat. Tunnel-ul folosește numai
conexiuni outbound, deci routerul nu primește reguli de port forwarding.
Configurează și o regulă Cloudflare Rate Limiting pentru hostname-ul public;
aceasta protejează inclusiv handshake-urile WebSocket înainte să ajungă la PC.

Pentru un tunnel administrat local există șablonul
`deploy/cloudflared-config.example.yml`. Copiază-l în afara Git, înlocuiește
UUID-ul, calea credentials și domeniile, apoi rulează:

```powershell
cloudflared tunnel --config C:\cale\config.yml run
```

Fișierul credentials și tokenul tunnel-ului sunt secrete și nu se adaugă în
repo. Configurațiile opționale `deploy/Caddyfile.example` și
`deploy/nginx.example.conf` arată rutarea celor două hostname-uri printr-un
proxy local; Caddy face upgrade WebSocket automat, iar șablonul Nginx îl declară
explicit. Cloudflare poate ruta și direct către porturile 8501/8000.

Referințe oficiale: [Cloudflare Tunnel setup](https://developers.cloudflare.com/tunnel/setup/)
și [Cloudflare WebSockets](https://developers.cloudflare.com/network/websockets/).

### Quick public access with Tailscale Funnel

Cea mai simplă pornire publică folosește launcherul:

```text
START_PUBLIC_TAILSCALE.bat
```

Launcherul face automat următoarele:

1. caută `tailscale.exe` în PATH și în directoarele standard Windows;
2. verifică dacă Tailscale este conectat și dacă dispozitivul este online;
3. verifică dacă versiunea instalată oferă comanda `tailscale funnel`;
4. configurează numai Streamlit pe Funnel HTTPS port 443;
5. pornește `start_server.bat` cu autentificarea OFF;
6. așteaptă health check-ul Streamlit și afișează URL-ul public final.

Rate limiting-ul și limitele de upload rămân active: 20 acțiuni UI/minut/client,
maximum 8 acțiuni UI simultane, 10 fișiere, 100 MB/fișier și 250 MB/upload.
FastAPI nu este publicat de acest launcher.

Dacă Tailscale lipsește, nu este autentificat sau Funnel nu poate fi activat,
launcherul nu deschide porturi și afișează comenzile manuale exacte. Instalarea
Windows se face de la [pagina oficială Tailscale](https://tailscale.com/download/windows).
După instalare și login, rulează launcherul din nou; dacă Tailscale cere
aprobarea Funnel, accept-o în pagina deschisă de CLI.

Linkul Funnel este public pe Internet. Distribuie-l numai persoanelor de
încredere: autentificarea este încă OFF, iar profilurile sunt fără parolă.
Oricine are linkul poate selecta sau crea profiluri. Oprirea expunerii publice:

```powershell
tailscale funnel --https=443 off
```

### Tailscale Funnel setup

Funnel oferă un URL public `*.ts.net` cu certificat HTTPS automat. Necesită
MagicDNS, HTTPS și permisiunea Funnel în politica tailnet. Dintr-un terminal
Administrator pe desktop:

```powershell
$env:FACULTY_COPILOT_DEPLOYMENT_MODE = "Public Internet"
$env:FACULTY_COPILOT_PUBLIC_URL = "https://NUME-DISPOZITIV.TAILNET.ts.net"
$env:FACULTY_COPILOT_PUBLIC_API_URL = "https://NUME-DISPOZITIV.TAILNET.ts.net:8443"
.\start_server.bat

tailscale funnel --bg --https=443 http://127.0.0.1:8501
tailscale funnel --bg --https=8443 http://127.0.0.1:8000
tailscale funnel status --json
```

Porturile publice Funnel permise sunt 443, 8443 și 10000. Pentru oprire:

```powershell
tailscale funnel --https=443 off
tailscale funnel --https=8443 off
```

Funnel este public, spre deosebire de Tailscale Serve. Dacă vrei numai prieteni
din tailnet, folosește `tailscale serve`, nu `tailscale funnel`.

Referință oficială: [Tailscale Funnel CLI](https://tailscale.com/docs/reference/tailscale-cli/funnel).
Pentru proxy local, Caddy documentează suportul WebSocket direct în
[`reverse_proxy`](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy).


## Co-pilot Facultate unified desktop app

Aplicatia recomandata pentru Windows este acum `Co-pilot Facultate.exe`. Este o
singura aplicatie care poate functiona in doua moduri:

- `Server mode`: ruleaza AI-ul pe acest PC, pornind Ollama, FastAPI, Streamlit si
  optional Cloudflare/Tailscale public access.
- `Client mode`: se conecteaza la un server existent si nu porneste Ollama,
  ChromaDB, modele locale sau procese server.

### Build Co-pilot Facultate.exe

Din folderul proiectului ruleaza:

```text
build_copilot_facultate.bat
```

Pentru un build de client care nu cere URL manual, configureaza URL-ul public
inainte de build prin una dintre variante:

```powershell
$env:FACULTY_COPILOT_DEFAULT_SERVER_URL = "https://linkul-tau-public"
.\build_copilot_facultate.bat
```

sau creeaza fisierul:

```text
desktop_app\default_server_url.txt
```

cu o singura linie:

```text
https://linkul-tau-public
```

URL-ul este inclus in executabil. Alternativ, poti pune acelasi fisier
`default_server_url.txt` langa `Co-pilot Facultate.exe` in `dist\`; aplicatia il
detecteaza la pornire. In acest caz, pe calculatoarele prietenilor alegerea
`Client mode` se conecteaza automat, fara ca ei sa introduca URL-ul.

Pentru distributie catre utilizatori normali, include URL-ul permanent de
productie. La dublu-click, aplicatia deschide direct interfata AI in WebView,
fara ecran de configurare si fara sa verifice porturi locale.

Output:

```text
dist\Co-pilot Facultate.exe
```

Scripturile si aplicatiile vechi raman disponibile (`start_server.bat`,
`AI Study Copilot Server.exe`, `Faculty Copilot.exe`, Cloudflare/Tailscale
scripts), dar aplicatia preferata pentru utilizare normala este
`Co-pilot Facultate.exe`.

### Prima pornire

La prima pornire apare intrebarea:

```text
Cum vrei sa folosesti aplicatia?
```

Alege:

- `Server mode` pe desktopul cu RTX 3070, Ollama si documentele locale.
- `Client mode` pe laptopul/prietenul care doar se conecteaza la URL-ul tau.

Aplicatia tine minte alegerea. La urmatorul double-click:

- in Server mode porneste serverul si deschide chat-ul cand Streamlit este gata;
- in Client mode se conecteaza la URL-ul salvat sau la URL-ul implicit inclus in
  executabil si deschide chat-ul in fereastra.

Tema implicita este `Dark mode`. Din primul ecran si din `Settings` poti alege
`Dark mode`, `Light mode` sau `Auto`; alegerea este salvata local si aplicata la
urmatoarea pornire.

### Server mode

Server mode porneste si monitorizeaza:

- Ollama;
- FastAPI pe portul 8000;
- Streamlit pe portul 8501;
- optional Cloudflare Tunnel sau Tailscale Funnel.

Pagina de status arata Local URL, LAN URL si Public URL daca exista. Public
access se porneste din butoanele `Enable Public` / `Disable Public` sau automat
cand `Auto Public Access` este activat in Settings.

Aplicatia nu incarca WebView-ul Streamlit pana cand `http://localhost:8501`
raspunde corect si frontend-ul este gata. Daca Streamlit ramane blocat pe
mesajul `Network issue: Cannot load Streamlit frontend code`, foloseste din
ecranul de status sau recovery:

- `Reload app` pentru reincarcarea interfetei;
- `Clear WebView cache and reload` dupa update/rebuild Streamlit sau dupa ce
  frontend-ul ramane cu fisiere vechi in cache.

Launcherul evita pornirea mai multor procese Streamlit pe acelasi port; daca
portul 8501 este deja activ, il refoloseste. In log apar mesajele pentru
procesul Streamlit pornit/refolosit, health check, URL-ul incarcat in WebView,
cache clear si eventualele erori de incarcare frontend.

### Client mode

Client mode foloseste automat URL-ul salvat sau URL-ul implicit inclus in build.
Daca exista URL configurat, fereastra se creeaza direct pe acel URL si chat-ul se
incarca imediat, ca o aplicatie desktop de tip ChatGPT/Claude. Client mode nu
porneste si nu asteapta Ollama, FastAPI, Streamlit sau ChromaDB local.

Health check-ul clientului este unul singur, usor, in fundal, cu timeout scurt.
Daca serverul este indisponibil, utilizatorul vede mesajul:

```text
Serverul nu este disponibil momentan.
```

cu butoanele `Retry` si `Open Settings`, fara erori tehnice brute.

Setarea URL-ului este ascunsa pentru utilizatori normali. Pentru modificari:
`Settings -> Developer Mode -> Advanced -> Server URL`. Daca nu exista niciun URL
configurat, acel fallback poate fi folosit pentru depanare, de exemplu:

```text
https://study.example.com
https://numele-tau.trycloudflare.com
http://192.168.1.50:8501
```

Pentru linkuri publice foloseste HTTPS. Clientul pastreaza sesiunea/cookie-urile
WebView intre lansari si nu salveaza parole in config.

Configuratia principala salvata local foloseste campurile:

```json
{
  "app_mode": "server | client",
  "default_server_url": "https://linkul-tau-public",
  "developer_mode": false,
  "remember_session": true,
  "theme": "dark"
}
```

### Reset saved settings

Din aplicatie: `Settings -> Reset saved setup`.

Alternativ, porneste executabilul cu `--reset` sau sterge fisierul:

```text
%APPDATA%\Co-pilot Facultate\settings.json
```

Cookie-urile WebView sunt in:

```text
%APPDATA%\Co-pilot Facultate\webview_profile\
```

## Windows Server Launcher

AI Study Copilot Server Launcher este aplicația desktop Windows pentru
administrarea serverului fără comenzi PowerShell. Controlează separat Ollama,
FastAPI, Streamlit și opțional Cloudflare Quick Tunnel sau Tailscale Funnel.
Scripturile existente rămân disponibile.

### Build launcher

1. Instalează Python 3.11 sau 3.12 și pregătește proiectul normal.
2. Rulează prin dublu-click build_server_launcher.bat.
3. Scriptul creează un mediu PyInstaller separat și produce:

   dist\AI Study Copilot Server.exe

Executabilul nu include Ollama, modelele sau documentele. El trebuie păstrat în
folderul dist al proiectului ori configurat din Settings către folderul corect
al repository-ului.

### Utilizare launcher

- Start All pornește Ollama, FastAPI și Streamlit în fundal, apoi tunnelul ales.
  Serviciile care răspund deja la health check nu sunt duplicate.
- Stop All oprește procesele pornite de launcher. Un serviciu găsit deja pornit
  din exterior este lăsat neatins.
- Restart All, Open App, Copy Public Link și Open Logs oferă operațiile uzuale
  fără terminal.
- Statusurile sunt verificate la aproximativ 7 secunde prin Ollama /api/tags,
  FastAPI /health și Streamlit /_stcore/health.
- Settings salvează folderul proiectului, porturile, tunnelul preferat (none,
  cloudflare, tailscale), pornirea minimizată, pornirea cu Windows, auto-start
  server, Auto Public Access și auto-restart.

Secțiunea Public Access are status Online/Offline, URL-ul HTTPS și butoane pentru
Enable, Disable, Restart, Copy și Open. Când Auto Public Access este activ,
Start All pornește automat și tunnelul preferat, fără PowerShell.

Pentru Cloudflare, launcherul verifică mai întâi lista de Named Tunnels. Dacă
găsește un tunnel și un config în %USERPROFILE%\.cloudflared\config.yml cu
hostname public, îl pornește și afișează URL-ul stabil. În lipsa unei configurații
complete folosește automat Quick Tunnel și extrage URL-ul trycloudflare.com din
output. Pentru Tailscale, launcherul reutilizează un Funnel deja configurat sau
îl activează și citește URL-ul permanent din status.

Setările sunt păstrate în
%LOCALAPPDATA%\AI Study Copilot\server_launcher.json, iar logul persistent și
URL-ul public sunt în storage\runtime. Cloudflare folosește un Quick Tunnel
către Streamlit 8501. Tailscale necesită aplicația conectată, MagicDNS și
permisiunea Funnel. Linkurile publice trebuie distribuite numai persoanelor de
încredere; nu se activează router port forwarding.

### Troubleshooting launcher

- Ollama missing: instalează Ollama pentru Windows și redeschide launcherul.
- .venv missing: rulează o singură dată install.ps1 din folderul proiectului.
- cloudflared missing: rulează winget install --id Cloudflare.cloudflared.
- Tailscale is not online: deschide Tailscale, autentifică-te și verifică
  permisiunea Funnel în tailnet.
- Port ocupat: schimbă porturile în Settings sau oprește procesul străin.
- Pentru servicii căzute activează Auto-restart crashed services; detaliile apar
  în panoul Logs și în storage\runtime\server_launcher.log.
- Dacă PyInstaller nu poate instala dependențele, verifică accesul la Internet
  și rulează din nou build_server_launcher.bat.

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
PATCH  /documents/{file_name}
DELETE /documents/{file_name}
DELETE /documents
POST   /documents/{file_name}/reindex
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

### Faculty Copilot desktop client

Pentru prieteni sau colegi care vor o aplicatie Windows normala, foloseste noul
client din `desktop_client/`. Clientul este doar un wrapper nativ WebView2 peste
interfata web a serverului:

- nu ruleaza Ollama;
- nu ruleaza ChromaDB;
- nu descarca modele AI;
- nu indexeaza documente local;
- pastreaza login-ul/cookie-urile serverului intre porniri.

La prima pornire, aplicatia cere `Server URL`, de exemplu:

```text
https://study.example.com
https://numele-tau.trycloudflare.com
https://NUME-DISPOZITIV.TAILNET.ts.net
```

Pentru linkuri publice foloseste HTTPS. Clientul permite `http://localhost` si
adrese LAN/Tailscale private pentru testare, dar afiseaza avertizare daca se
introduce HTTP pentru un host public.

#### Build desktop client

Pe PC-ul unde este repo-ul, ruleaza:

```text
build_desktop_client.bat
```

Output principal:

```text
dist\Faculty Copilot.exe
```

Daca Inno Setup este instalat, scriptul creeaza optional si:

```text
dist\Faculty Copilot Setup.exe
```

Executabilul rezultat este aplicatia pe care o pui in GitHub Releases. Pe
Windows 11, WebView2 este de obicei deja instalat. Daca un client nu are WebView2,
instaleaza Microsoft Edge WebView2 Runtime.

#### Cum foloseste utilizatorul aplicatia

1. Descarca `Faculty Copilot.exe` sau `Faculty Copilot Setup.exe` din GitHub
   Releases.
2. Deschide aplicatia `Faculty Copilot`.
3. Introduce URL-ul public HTTPS al serverului.
4. Apasa `Connect`.
5. Login-ul apare exact ca in aplicatia de pe server, iar sesiunea ramane salvata
   in profilul WebView2 local.

Daca serverul nu raspunde, clientul afiseaza un ecran prietenos cu `Retry` si
permite schimbarea URL-ului. Nu blocheaza fereastra si nu porneste niciun proces
AI local.

Din meniu:

```text
Faculty Copilot -> Settings
Faculty Copilot -> Reload
Faculty Copilot -> Logout
Faculty Copilot -> Fullscreen
```

Setarile clientului sunt salvate in:

```text
%APPDATA%\Faculty Copilot\client_config.json
```

Cookie-urile si sesiunea WebView2 sunt salvate separat in:

```text
%APPDATA%\Faculty Copilot\webview_profile\
```

Nu salva parole in config. Parolele si sesiunile sunt responsabilitatea paginii
de login de pe server.

#### Publicare pe GitHub Releases

Pentru distributie:

1. Porneste serverul pe desktop cu launcherul/serverul existent.
2. Expune Streamlit prin Cloudflare Tunnel sau Tailscale Funnel, nu prin port
   forwarding brut.
3. Construieste clientul cu `build_desktop_client.bat`.
4. In GitHub, mergi la `Releases -> Draft a new release`.
5. Ataseaza `dist\Faculty Copilot.exe` sau `dist\Faculty Copilot Setup.exe`.
6. Scrie in release URL-ul pe care trebuie sa il introduca utilizatorii, daca
   este deja stabil.

Recomandat pentru prieteni: Cloudflare Tunnel cu domeniu/URL HTTPS stabil.
Clientul vechi din `client_app/` si `build_client.bat` ramane disponibil pentru
compatibilitate LAN/Tailscale, dar distributia recomandata este `Faculty
Copilot.exe`.

#### Instalarea unui utilizator nou (auth ON)

Utilizatorul nou nu are nevoie de Python, Ollama, modele sau ChromaDB pe laptop:

1. Administratorul creeaza contul pe desktop, din folderul proiectului:

```powershell
.\.venv\Scripts\python.exe manage_users.py ana --password "o-parola-lunga"
```

Comanda afiseaza si un token API. Trimite parola sau tokenul printr-un canal
privat; nu le adauga in Git si nu le publica.

2. Administratorul porneste serverul pe desktopul cu RTX 3070.
3. Se descarca sau se instaleaza numai `Faculty Copilot.exe` din release-ul
   Windows.
4. La prima pornire se introduce URL-ul HTTPS public al serverului.
5. In fereastra aplicatiei se introduc utilizatorul si parola/tokenul. Acest pas
   nu apare cand `FACULTY_COPILOT_AUTH_ENABLED=0`.
6. Cursurile se aleg cu uploaderul din interfata web afisata in aplicatie.

Toti utilizatorii folosesc acelasi GPU si aceeasi coada, dar au directoare de
documente, colectii Chroma si baze SQLite de memorie separate.

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

Pentru acces privat folosește Tailscale Share/Serve. Pentru un URL public
folosește configurațiile Cloudflare Tunnel sau Tailscale Funnel de mai sus.
Ambele termină HTTPS înainte de serviciile locale și nu necesită port forwarding.

FastAPI poate termina și TLS direct dacă ai certificat și cheie locală:

```powershell
$env:FACULTY_COPILOT_SSL_CERTFILE = "C:\cale\cert.pem"
$env:FACULTY_COPILOT_SSL_KEYFILE = "C:\cale\key.pem"
.\start_server.bat
```

Aceste variabile se aplică API-ului de pe portul 8000. Pentru interfața
Streamlit de pe 8501, termină HTTPS în tunnel sau reverse proxy.

Aceeasi arhitectura poate fi folosita mai tarziu pentru macOS, Linux, Android
si iPhone: clientii trebuie doar sa afiseze Streamlit-ul serverului sau sa
apeleze API-ul FastAPI.

## Documente si baza de date

Folderul implicit pentru documente este:

```text
documents/
```

Acesta este folosit numai în modul intern `local`. În modul cu profiluri sau
auth ON, fiecare profil/cont are:

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

Memoria de studiu a profilului curent este salvată local în:

```text
storage/users/<username>/memory/study_memory.sqlite3
```

Workspace-ul intern `local` păstrează compatibil baza veche în
`storage/memory/study_memory.sqlite3`.

In aceeasi baza SQLite sunt salvate si:

- metadatele academice editabile pentru documente: an, materie, curs;
- planurile de sesiune generate;
- zilele planificate si documentele incluse;
- preferintele locale ale aplicatiei.

Fișierul colecției active pentru un profil este:

```text
storage/users/<username>/active_collection.txt
```

Workspace-ul intern `local` păstrează compatibil `storage/active_collection.txt`.

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
PATCH /documents/{file_name}
DELETE /documents/{file_name}
DELETE /documents
POST /documents/{file_name}/reindex
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

Cu `FACULTY_COPILOT_AUTH_ENABLED=0` (implicit), endpoint-urile nu cer parolă.
Pentru izolare passwordless, clientul poate trimite profilul dorit:

```http
X-User-Profile: stxfanee
```

Dacă headerul lipsește, API-ul folosește fallback-ul compatibil
`default_user`. Cu `FACULTY_COPILOT_AUTH_ENABLED=1`, toate endpoint-urile, cu
excepția `/health` și `/auth/login`, cer autentificare:

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
