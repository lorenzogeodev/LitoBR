# Changelog / Registro de alterações

## 1.0.2
Interface mais simples e mapa mais legível. / Simpler interface and more readable maps.

- Abas com nomes claros, linha dizendo qual área vai ser baixada e opções avançadas recolhidas.
- Aviso de "Pronto" dentro da janela; botão de recomendação só quando há mapa mais detalhado.
- Unidades diferentes não saem mais com a mesma cor na paleta de reserva (as cores oficiais não mudam).
- Camada do pacote com nome legível ("Litologia, Bahia") no lugar do nome do arquivo.
- Legenda de status mais clara (Recente / Antigo) e textos que apareciam cortados.

## 1.0.1
Enums do QGIS escopados para o Qt6 (QGIS 4), como pede o checador da loja do QGIS. / QGIS enums scoped for Qt6.

## 1.0.0
Primeira versão pública. / First public release.

- Serviços REST do SGB/CPRM, pacotes do RIGeo (26 estados e 16 províncias minerais) e BDIA/IBGE.
- Recorte pela tela, por uma camada de máscara, ou sem recorte.
- Paleta oficial do SGB (5.385 unidades), com paleta de reserva por litologia e idade.
- Recomendação do produto mais detalhado para a área do mapa.
- Escala, ano e referência ABNT NBR 6023 gravados nos metadados da camada.
- Preparado para QGIS 3.22+ e QGIS 4 (Qt6).
