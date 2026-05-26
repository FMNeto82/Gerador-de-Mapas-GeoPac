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

Acesse `http://127.0.0.1:5000`.

## Publicacao em VPS

1. Envie este projeto para a VPS.
2. Instale Python 3.11 ou superior.
3. Instale as dependencias com `pip install -r requirements.txt`.
4. Execute o app em uma porta interna, por exemplo `python app.py`.
5. Configure Nginx ou Apache como proxy reverso para essa porta.

Em producao, altere `app.secret_key` em `app.py` para um valor exclusivo do servidor.
