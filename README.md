# Vorbereitungen
## Live- oder Test-Server
In der .env-Datei im Ordner "synchronization" kann angegeben werden, ob das Projekt auf den Live-Publikationsserver hochgeladen werden soll oder zuerst nur testweise auf den Test-Server unter "epub-test.ur.de".
## Nutzerdaten hinterlegen
- Unix: Datei `.netrc` in `/home/<user>` erstellen    
- Windows: Datei `_netrc` in `%userprofile%` (Alias für `C:\Users\<user>`) erstellen

Inhalt: `machine <example.com> login <username> password <password>`     
z.B.: `machine epub.uni-regensburg.de login nds1234 password 1234`

Es können auch mehrere Anmeldeinformationen eingetragen werden, die von einer Leerzeile getrennt werden müssten.    
```
machine epub.uni-regensburg.de login nds1234 password 1234

machine epub-test.uni-regensburg.de login nds1234 password 1234
```

Zusätzlich unter Unix: `chmod og-rwx ~/.netrc`

## Python-Pakete installieren
Notwendige Pakete installieren:     
`pip install -r [PFAD]/DTSsynchronization/synchronization/requirements.txt`

# Skript manuell starten
Unter Unix zuerst Berechtigungen vergeben: `chmod a+x [PFAD]/DTSsynchronization/synchronization/eprints_sword.py`    

Skript manuell ausführen (als Administrator unter Windows):       
`python "[PFAD]/DTSsynchronization/synchronization/eprints_sword.py" -p [PFAD]/colorlearning -v` oder `python synchronization/eprints_sword.py -p example_data/torquelearning/ -v`

Optionale Parameter:
- `--force`: Überschreibt bestehende Dateien
- `--auto`: Unterbindet die manuelle Bestätigung und Prüfung der korrekten EPRINT-ID

# Skript automatisieren
## Windows
### Skript anlegen
Eine Datei "update_sword.cmd" anlegen (z.B. im Ordner "DTSsynchronization\synchronization") und folgendes hineinschrieben: `python "[PFAD]\DTSsynchronization\synchronization\eprints_sword.py" -p [PFAD]\colorlearning -v --auto`    

Eine Beispiel-Datei mit dem Titel `update_sword.cmd` liegt schon bereit.
### Aktion erstellen
"Aufgabenplanung" unter Windows aufrufen und "Aufgabe erstellen"     
- **Allgemein**:
	- Beliebigen "Namen" eingeben   
	- "Mit höchsten Privilegien ausführen" aktivieren
	- "Konfigurieren für" und das laufende Betriebssystem auswählen (siehe [berechtigungen_task.PNG](https://github.com/brembslab/DTSsynchronization/blob/main/installation/berechtigungen_task.PNG))
- **Trigger**: beliebiger Trigger, z.B. "Bei Anmeldung"
- **Aktionen**:
	- "Neu" 
	- *Programm/Skript*: `[PFAD]\DTSsynchronization\synchronization\update_sword.cmd`
	- *Argumente hinzufügen (optional)*: `> [PFAD]\DTSsynchronization\synchronization\log.txt 2>&1`
## Unix
Zuerst überprüfen, ob ein Skript nach dem Booten ausgeführt werden darf:
1. `sudo systemctl status cron.service`
2. Um es zu aktivieren: `sudo systemctl enable cron.service`    

Einen *cronjob* anlegen:
1. `crontab -e`
2. `@reboot python [PFAD]/DTSsynchronization/synchronization/eprints_sword.py --auto > [PFAD]/DTSsynchronization/synchronization/log.txt 2>&1`

# YAML-Datei
## Mögliche Werte
`oa.type['name']: primary, gold_paid, gold_free, gold_olh, scoap, hybrid, offsetting, rsc, alliance, copyright_law, sherpa, before1994, individual_contract, no_oa, unknown, other`    

`subject['id']: ddc_2_570`        

`department['id'']: fak11_02_09`        

`data.type['name']: dataset, article, book_section, monograph, conference_item, book, thesis_rgbg, thesis, teaching_resource, video, image, audio, experiment, software, patent, journal, translation, other`     

`received.funding: yes, no`    

`acknowledged.funders: yes, no, no_funders`   

`ispublished: unknown, pub, inpress, submitted, unpub`

`refereed: unknown, yes, not_yet, never`

# TODOS
- [ ] https://github.com/brembslab/DTSsynchronization/security/dependabot
- [ ] Der Lizenz-Wert kann nur im fertigen XML ersetzt werden (Download bspw. https://epub.uni-regensburg.de/cgi/export/eprint/58196/XML/epub-eprint-58196.xml)
