# LitoBR

**Brazilian geological open data in QGIS: downloaded, clipped and styled in one click.**
*Dados geológicos abertos do Brasil no QGIS: baixados, recortados e estilizados em um clique.*

![license](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)
![qgis](https://img.shields.io/badge/QGIS-3.22%2B%20%7C%204.x-green)
![ci](https://github.com/lorenzogeodev/LitoBR/actions/workflows/ci.yml/badge.svg)

[English](#english) · [Português](#português)

---

## English

LitoBR is a QGIS plugin that brings the public geological data of Brazil straight into your project.
It talks to the open services of the Geological Survey of Brazil (SGB/CPRM) and of IBGE, so you do not
have to hunt for links, unzip packages or build legends by hand.

> Independent project. LitoBR is not affiliated with or endorsed by SGB/CPRM or IBGE.
> The data belong to their providers and follow their terms of use.

### What it does

- **Cloud tab:** lithostratigraphy at several scales (1:1,000,000 down to 1:50,000, plus state maps),
  structures, mineral resources, outcrops, SIAGAS wells, aquifers, geosites, caves and the BDIA/IBGE
  1:250,000 geology.
- **RIGeo tab:** GIS packages of 26 state geological maps and 16 mineral provinces
  (Quadrilátero Ferrífero, Carajás, Tapajós, Seridó and others).
- **Area:** clip to the map canvas, to a mask layer, or load everything.
- **Recommendation:** products that cover the current map area get a ★, and one button picks the most
  detailed one.
- **Style:** official colour palette published by SGB (5,385 units, matched by unit ID or symbol). Units
  with no official colour fall back to a palette by lithology and age.
- **Traceability:** scale, year and an ABNT NBR 6023 citation are stored in the metadata of each layer.
- **Status dots:** green (2014 or newer), amber (legacy), blue (continuously updated), grey (no year).

### Install

- **QGIS Plugin Manager (recommended):** *Plugins → Manage and Install Plugins*, search for **LitoBR**.
  While the plugin is flagged experimental, tick *Show also experimental plugins* in *Settings*.
- **From ZIP:** download `litobr.zip` from the [releases](https://github.com/lorenzogeodev/LitoBR/releases)
  page, then *Plugins → Manage and Install Plugins → Install from ZIP*.

The plugin lives in the **Vector → LitoBR** menu and in the toolbar.

### Requirements and limits

- QGIS 3.22 or newer, including QGIS 4. No external Python libraries.
- Internet connection. Data cover Brazil only.
- The interface is in Brazilian Portuguese.
- RIGeo packages are always downloaded whole; the clip applies to what is loaded into the project.
- Paraíba has no GIS package in RIGeo, and the state of the map is estimated from bounding boxes, so it
  can be wrong near state borders.

### Data sources

| Source | What | Access |
|---|---|---|
| SGB/CPRM GeoPortal | Geology, structures, mineral resources, hydrogeology | ArcGIS REST |
| SGB/CPRM RIGeo | State maps and mineral province packages | DSpace API |
| IBGE BDIA | Geology 1:250,000 | WFS |

All addresses are in [`litobr/catalogo.json`](litobr/catalogo.json). If a service moves, that file is the
only thing to edit.

### Development

```bash
python3 -m pytest tests     # unit tests of the pure modules (no QGIS needed)
python3 build.py            # repository checks + dist/litobr.zip
python3 build.py --release  # same, and fails if metadata placeholders remain
```

The work that runs in the background task (`servicos.py`) only touches network and disk. Layers, canvas
and windows are handled on the main thread. Network goes through the QGIS network manager, so proxy and
certificate settings are respected. The tests do not cover the interface or the PyQGIS calls.

Bug reports and ideas are welcome in the [issue tracker](https://github.com/lorenzogeodev/LitoBR/issues).

### License

GPL-3.0-or-later. See [LICENSE](LICENSE).

---

## Português

O LitoBR é um complemento do QGIS que traz os dados geológicos públicos do Brasil direto para o projeto.
Ele conversa com os serviços abertos do Serviço Geológico do Brasil (SGB/CPRM) e do IBGE, sem precisar
caçar link, descompactar pacote ou montar legenda na mão.

> Projeto independente. O LitoBR não tem vínculo com o SGB/CPRM nem com o IBGE, nem é endossado por eles.
> Os dados pertencem aos provedores e seguem os termos de uso de cada um.

### O que faz

- **Aba Nuvem:** litoestratigrafia em várias escalas (de 1:1.000.000 a 1:50.000, mais os mapas estaduais),
  estruturas, recursos minerais, afloramentos, poços SIAGAS, aquíferos, geossítios, cavernas e a geologia
  1:250.000 do BDIA/IBGE.
- **Aba RIGeo:** pacotes SIG de 26 mapas geológicos estaduais e 16 províncias minerais
  (Quadrilátero Ferrífero, Carajás, Tapajós, Seridó e outras).
- **Área:** recorta pela tela, por uma camada de máscara, ou carrega tudo.
- **Recomendação:** os produtos que cobrem a área do mapa ganham uma ★, e um botão escolhe o mais
  detalhado.
- **Estilo:** paleta oficial publicada pelo SGB (5.385 unidades, reconhecidas pelo código ou pela sigla).
  Unidade sem cor oficial cai numa paleta por litologia e idade.
- **Rastreabilidade:** escala, ano e a referência ABNT NBR 6023 ficam nos metadados de cada camada.
- **Bolinhas de status:** verde (2014 em diante), âmbar (legado), azul (atualização contínua), cinza
  (sem ano).

### Instalar

- **Pelo QGIS (recomendado):** *Complementos → Gerenciar e instalar complementos*, procure **LitoBR**.
  Enquanto o complemento estiver marcado como experimental, ative *Mostrar também os complementos
  experimentais* em *Opções*.
- **Pelo ZIP:** baixe o `litobr.zip` na página de
  [releases](https://github.com/lorenzogeodev/LitoBR/releases) e use *Instalar a partir do ZIP*.

O complemento fica no menu **Vetor → LitoBR** e na barra de ferramentas.

### Requisitos e limites

- QGIS 3.22 ou mais novo, inclusive o QGIS 4. Sem bibliotecas Python externas.
- Precisa de internet. Os dados cobrem só o Brasil.
- Os pacotes do RIGeo sempre são baixados inteiros; o recorte vale para o que entra no projeto.
- A Paraíba não tem pacote SIG no RIGeo, e a UF da área é estimada pelo retângulo envolvente de cada
  estado, então pode errar perto de divisa.

### Se algo der errado

Abra *Exibir → Painéis → Mensagens de log*, aba **LitoBR**, e cole o texto numa
[issue](https://github.com/lorenzogeodev/LitoBR/issues).

### Licença

GPL-3.0-or-later. Veja [LICENSE](LICENSE).
