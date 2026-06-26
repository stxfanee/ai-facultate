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
- Selecteaza documente prin dialog nativ Windows.
- Indexeaza PDF, DOCX si PPTX in ChromaDB.
- Raspunde exclusiv pe baza documentelor indexate.
- Afiseaza lista completa de documente indexate.
- Organizeaza documentele pe `An -> Materie -> Curs`.
- Permite editarea metadatelor academice pentru fiecare document indexat.
- Detecteaza intrebari despre un curs anume, de exemplu `despre ce este cursul 1`.
- Filtreaza retrieval-ul la documentul cerut cand intrebarea mentioneaza un curs/PDF.
- Pastreaza retrieval semantic global pentru intrebari de continut.
- Ofera moduri de raspuns `Fast`, `Balanced` si `Accurate`.
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
  START_SERVER.bat
  api_server.py
  README.md
  study_memory.py
  documents/
  storage/
    chroma/
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

Tab-ul `Intrebari` contine patru moduri:

1. `Intrebare normala` pentru intrebari RAG globale.
2. `Compara cursuri` pentru selectarea si compararea a cel putin doua documente.
3. `Rezumat document` pentru rezumatul unui singur document.
4. `Cauta in document specific` pentru retrieval limitat la documentul ales.

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

In sidebar, controlul `Mod raspuns` ofera:

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

Butonul `Genereaza orar .ics` creeaza local un fisier calendar `.ics`. Nu exista
integrare cu Google Calendar sau cloud. Fisierul poate fi importat manual in
aplicatia ta de calendar, daca vrei.

## Access from phone/laptop

PC-ul desktop este serverul. Ollama, modelele Qwen, embeddings, ChromaDB,
memoria SQLite si inferenta pe RTX 3070 ruleaza numai pe desktop.

Telefonul sau laptopul afiseaza doar interfata Streamlit in browser. Nu instala
si nu rula Ollama sau modelele pe telefon/laptop.

Selectarea fisierelor prin dialogul Windows si indexarea initiala se fac de pe
desktopul server. Dupa indexare, telefonul/laptopul poate folosi intrebarile,
rezumatele, comparatiile, flashcards, quizurile si progresul.

1. Porneste Ollama pe desktop.
2. Pe desktop, da dublu click pe:

```text
START_SERVER.bat
```

3. Aplicatia porneste pe `0.0.0.0`, portul fix `8501`.
4. In aplicatie, sectiunea `Acces server` afiseaza:

```text
Local: http://localhost:8501
LAN: http://ADRESA_PC:8501
Tailscale: http://ADRESA_TAILSCALE:8501
```

5. Pentru un telefon/laptop din aceeasi retea Wi-Fi, deschide URL-ul `LAN`.
6. Pentru acces din afara casei, instaleaza Tailscale pe desktop si pe client,
   autentifica ambele dispozitive in aceeasi retea Tailscale si foloseste URL-ul
   `Tailscale` afisat de aplicatie.

La prima pornire, Windows Firewall poate cere permisiune. Permite accesul numai
pentru retele private de incredere.

**AVERTISMENT: Nu expune portul 8501 direct pe internetul public. Nu configura
port forwarding in router. Pentru acces remote foloseste Tailscale.**

## Documente si baza de date

Folderul implicit pentru documente este:

```text
documents/
```

Baza ChromaDB este salvata local in:

```text
storage/chroma/
```

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

## API optional pentru o aplicatie mobila viitoare

Fisierul `api_server.py` adauga un backend FastAPI optional. Streamlit ramane
interfata principala si nu este inlocuit.

Endpoint-uri:

```text
POST /ask
POST /quiz
POST /flashcards
GET  /documents
GET  /health
```

Endpoint-urile `POST` accepta optional:

```json
{
  "response_mode": "Balanced"
}
```

Valorile permise sunt `Fast`, `Balanced` si `Accurate`.

Pornire locala pentru dezvoltare:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api_server:app --host 127.0.0.1 --port 8000
```

Documentatia interactiva FastAPI este disponibila la:

```text
http://127.0.0.1:8000/docs
```

API-ul foloseste acelasi Ollama, aceeasi baza ChromaDB si aceeasi memorie locala
de pe desktop. Pentru testare de pe alt dispozitiv, foloseste numai o retea
privata de incredere sau Tailscale. Nu expune nici portul API direct pe
internetul public.

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
