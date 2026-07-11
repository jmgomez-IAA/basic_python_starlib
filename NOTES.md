# Hallazgos y trabajo futuro

## [IMPORTANTE] Tráfico propio del HK contamina los contadores del puerto de conexión

**Fecha**: 2026-07-11
**Contexto**: `11_essential_hk_service.py`, análisis de `gr718b_export_pivot.csv`

### Hallazgo

El puerto físico por el que el Brick Mk3 está conectado al GR718B (puerto 17 en
el montaje actual) muestra tráfico perfectamente periódico y determinista en
sus contadores `outgoing_chars`/`incoming_chars`: exactamente **+534 bytes
salientes** y **+102 bytes entrantes** en cada ciclo de 10s, sin ninguna
desviación.

Verificado matemáticamente: estos valores coinciden EXACTOS con la suma de
los tamaños de las 6 transacciones RMAP que el propio servicio HK Esencial
genera cada ciclo (comando fijo de 17B cada uno = 102B entrantes; respuestas
de 12B cabecera + datos + 1B CRC, sumando 534B salientes).

**Conclusión**: no hay tráfico real de instrumento en este momento. Lo que
miden los contadores del puerto de conexión al Brick es, en su totalidad,
el propio tráfico de monitorización RMAP — un efecto de observador: medir el
puerto lo perturba, porque la medición pasa físicamente por ese mismo puerto.

### Por qué importa

Si en el futuro se conecta un instrumento real y se analiza el tráfico del
puerto de conexión (para detección de anomalías, throughput, etc.), esta
componente determinista debe poder distinguirse del tráfico genuino del
instrumento, o contaminará cualquier análisis/modelo que use esos contadores
como feature.

### Action item — trabajo futuro

- [ ] Mantener un **contador propio del tráfico HK generado** (bytes
      exactos por ciclo, calculables de antemano a partir de la tabla de
      comandos RMAP en uso — ver fórmula en el análisis del 2026-07-11) para
      poder diferenciarlo del tráfico normal del instrumento en el puerto de
      conexión.
- [ ] Uso previsto: **visualización y control** (dashboards, verificación de
      que el tráfico observado no es solo ruido propio) — **no** como input
      del pipeline de inferencia/ML. El modelo de detección de anomalías no
      debería necesitar esta corrección si se entrena sobre puertos que NO
      son el de conexión al Brick, o si se resta esta componente conocida
      antes de la extracción de features en los puertos que sí lo son.
- [ ] Documentar también esta limitación en la tesis (candidato:
      `docs/simulacion_gr718b_contexto.md` o una sección nueva de
      limitaciones de la campaña de monitorización real), ya que afecta a la
      interpretación de cualquier dato de tráfico capturado en el puerto de
      conexión física.
