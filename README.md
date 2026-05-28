# Gerador de Mapas LT Ponta Grossa - Canoinhas

Aplicativo web em Flask para gerar o mapa de pontos de controle e caminhamentos terrestres da LT 500kV Ponta Grossa - Canoinhas.

## O que o aplicativo faz

- Baixa a planilha de pontos de controle do Google Sheets a cada nova geracao do mapa.
- Usa o arquivo KML do eixo da LT salvo em `Vetores/LT230kV PGR-CAN.kml`.
- Usa todos os arquivos `.kml`, `.kmz` e `.gpx` em `Vetores/Caminhamentos Terrestres`, incluindo subpastas, para desenhar os caminhamentos.
- Mantem a regra atual de calculo dos quilometros percorridos, sem remover os caminhamentos exibidos no mapa.
- Gera o arquivo `Mapa_Campo_LT_PGR_CAN.html`.
- Pode sincronizar automaticamente os caminhamentos de uma pasta publica do Google Drive antes da geracao.

## Como rodar localmente

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Acesse `http://127.0.0.1/gerador_de_mapas`.

Para sincronizar os caminhamentos do Google Drive e gerar o mapa:

```bash
python sync_drive_tracks.py
```

Por padrao, o script usa a pasta publica:

```text
https://drive.google.com/drive/folders/1L035wiodAQnAHhvHYEHu0Q4lniZL6nhf
```

Para usar outra pasta, defina `LOCUS_DRIVE_FOLDER_ID`.

## Publicacao em VPS

Exemplo para Ubuntu/Debian:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip
sudo mkdir -p /var/www
sudo git clone https://github.com/FMNeto82/Gerador-de-Mapas-GeoPac.git /var/www/Gerador-de-Mapas-GeoPac
cd /var/www/Gerador-de-Mapas-GeoPac
sudo python3 -m venv .venv
sudo .venv/bin/pip install -r requirements.txt
sudo chown -R www-data:www-data /var/www/Gerador-de-Mapas-GeoPac
sudo cp deploy/gerador-mapas.service /etc/systemd/system/gerador-mapas.service
sudo cp deploy/gerador-mapas-sync.service /etc/systemd/system/gerador-mapas-sync.service
sudo cp deploy/gerador-mapas-sync.timer /etc/systemd/system/gerador-mapas-sync.timer
sudo systemctl daemon-reload
sudo systemctl enable --now gerador-mapas
sudo systemctl enable --now gerador-mapas-sync.timer
```

O aplicativo fica disponivel em `http://IP-DA-VPS/gerador_de_mapas`.

A atualizacao automatica roda todos os dias as 19h no fuso `America/Sao_Paulo`.

Para testar a sincronizacao imediatamente:

```bash
sudo systemctl start gerador-mapas-sync.service
sudo journalctl -u gerador-mapas-sync.service -n 80 --no-pager
```

Se houver firewall ativo:

```bash
sudo ufw allow 80/tcp
```

Em producao, altere `app.secret_key` em `app.py` para um valor exclusivo do servidor.

## Integracao com Locus Map

O caminho recomendado para os caminhamentos e exportar os tracks do Locus Map como
`KML/KMZ` ou `GPX` e enviar os arquivos para o gerador. O Locus Map exporta tracks e
rotas nesses formatos, e o gerador ja consome os arquivos diretamente da pasta
`Vetores/Caminhamentos Terrestres`.

Fluxo de campo sugerido:

1. No Locus Map, grave o caminhamento normalmente.
2. Ao final, salve o track e exporte em `KML/KMZ` ou `GPX`.
3. Envie o arquivo pelo formulario do gerador ou sincronize a pasta de exportacao do
   celular com `mapa-campo-web/Vetores/Caminhamentos Terrestres`.
4. Clique em `Gerar mapa`.

Para automacao em Android, a biblioteca `asamm/locus-api` pode ser usada em um app
companheiro para iniciar, pausar e parar a gravacao de tracks por intents do Locus.
Essa abordagem e util quando se quer padronizar o nome do perfil de gravacao,
forcar salvamento automatico ao parar e depois compartilhar/sincronizar o arquivo
exportado para o servidor do gerador.
