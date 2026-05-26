# Gerador de Mapas LT Ponta Grossa - Canoinhas

Aplicativo web em Flask para gerar o mapa de pontos de controle e caminhamentos terrestres da LT 500kV Ponta Grossa - Canoinhas.

## O que o aplicativo faz

- Baixa a planilha de pontos de controle do Google Sheets a cada nova geracao do mapa.
- Usa o arquivo KML do eixo da LT salvo em `Vetores/LT230kV PGR-CAN.kml`.
- Usa todos os arquivos `.kml` e `.kmz` em `Vetores/Caminhamentos Terrestres` para desenhar os caminhamentos.
- Mantem a regra atual de calculo dos quilometros percorridos, sem remover os caminhamentos exibidos no mapa.
- Gera o arquivo `Mapa_Campo_LT_PGR_CAN.html`.

## Como rodar localmente

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Acesse `http://127.0.0.1:8081`.

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
sudo systemctl daemon-reload
sudo systemctl enable --now gerador-mapas
```

O aplicativo fica disponivel em `http://IP-DA-VPS:8081`.

Se houver firewall ativo:

```bash
sudo ufw allow 8081/tcp
```

Em producao, altere `app.secret_key` em `app.py` para um valor exclusivo do servidor.
