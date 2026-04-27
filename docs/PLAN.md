# Plan de 3 semanas — QlikView → Power BI migration

**Objetivo:** ejecutar el pipeline completo end-to-end sobre los samples de `data/input_qvw_samples/`, identificar bugs, y dejarlo listo para producción.

**Supuestos iniciales:**
- DocumentAnalyzer ya está en `document_analyzer/DocumentAnalyzer_V3.10.qvw` ✅
- Samples ya están en `data/input_qvw_samples/` ✅
- `settings.json` apunta a rutas correctas ✅
- Falta: `api_key` y `azure_endpoint` reales de Azure OpenAI (hoy son demo)

---

## Semana 1 — Setup, smoke test y desbloquear extracción

**Meta:** que el paso 1 (Metadata Extraction con QlikView + pyautogui) corra end-to-end sobre al menos **1 QVW**.

### Día 1 — Entorno
- [ ] Instalar/abrir QlikView Personal Edition una vez (acepta licencia)
- [ ] Abrir `DocumentAnalyzer_V3.10.qvw` manualmente y verificar que carga sin errores
- [ ] Crear venv + `pip install -r requirements.txt`
- [ ] Verificar que `streamlit run src/app.py` abre el dashboard sin crash
- [ ] Conseguir `api_key` + `azure_endpoint` de Azure OpenAI y actualizar `settings.json`

### Día 2 — Smoke test manual del Step 1
- [ ] Correr el pipeline eligiendo **1 solo QVW** (el más simple de `input_qvw_samples`)
- [ ] Observar `automate_qlikview` en vivo: ¿los clicks aciertan?
- [ ] Registrar la resolución de pantalla y DPI scaling de Windows
- [ ] Si falla: anotar en qué click falla exactamente

### Día 3 — Fix resolución/DPI (si el Día 2 falló)
- [ ] **Decidir enfoque:** image recognition (`locateOnScreen`) vs escalado proporcional
- [ ] Si image recognition: tomar screenshots de path_input, extract_button, open_log_button → guardar en `assets/ui_targets/`
- [ ] Implementar fix en [src/utils.py:473](src/utils.py#L473)
- [ ] Re-correr smoke test

### Día 4 — Batch test del Step 1
- [ ] Correr Step 1 sobre **los 5 QVWs más pequeños** de samples
- [ ] Verificar que `output/qvw_metadata/qvwork/` se llena con los CSVs esperados
- [ ] Documentar cualquier QVW que falle y por qué

### Día 5 — Buffer / retrospectiva Semana 1
- [ ] Arreglar bugs residuales del Step 1
- [ ] Escribir una mini checklist "cómo reproducir Step 1 desde cero"
- [ ] Commit de los fixes

**Criterio de salida semana 1:** Step 1 funciona sobre ≥5 QVWs sin intervención manual.

---

## Semana 2 — Pipeline Python puro (Steps 2–7)

**Meta:** correr todos los pasos que NO dependen de QlikView sobre los CSVs ya extraídos.

### Día 6 — XML Parsing + Field Mapping (Steps 2, 3)
- [ ] Correr Step 2 (XML Parsing) sobre la salida del Step 1
- [ ] Verificar `output/qvw_metadata_restructured/` tiene la estructura esperadal

- [ ] Correr Step 3 (Field Mapping) — revi  sar que `assets/field_mapping.csv` está al día
- [ ] Detectar campos no mapeados y añadirlos al CSV

### Día 7 — Data Source Creation (Step 4)
- [ ] Correr Step 4 sobre 1 QVW de referencia
- [ ] Validar que las M queries generadas son sintácticamente válidas
- [ ] Probar 1 M query pegándola manualmente en Power BI Desktop

### Día 8 — Expression to DAX (Step 5) ← crítico
- [ ] Verificar que la API key de Azure OpenAI funciona (test call simple)
- [ ] Correr Step 5 sobre 3 QVWs
- [ ] Revisar manualmente 10 DAX generados: ¿son válidos? ¿preservan semántica?
- [ ] Anotar patrones donde el LLM falla (ej. funciones Qlik sin equivalente directo)

### Día 9 — PDF Generation + Output Analysis (Steps 6, 7)
- [ ] Correr Step 6 — ojo: [src/utils.py:920](src/utils.py#L920) también usa pyautogui (Alt+tab + keypresses para exportar PDF desde QlikView). Validar que funciona
- [ ] Si el Step 6 falla por clicks, aplicar mismo fix que Semana 1
- [ ] Correr Step 7 (Output Analysis)

### Día 10 — Batch test completo Steps 1–7
- [ ] Correr pipeline completo sobre 10 QVWs
- [ ] Medir tiempo por paso
- [ ] Recolectar todos los errores en una tabla (QVW, step, error)

**Criterio de salida semana 2:** pipeline completo corre sobre ≥10 QVWs con tasa de éxito ≥80%.

---

## Semana 3 — Comparación, validación y hardening

**Meta:** validar calidad de salida, arreglar los edge cases y dejarlo listo para demo/handoff.

### Día 11 — Step 8: Comparison QlikView vs Power BI
- [ ] Abrir 1 reporte migrado en Power BI Desktop manualmente
- [ ] Comparar con el QVW original side-by-side (measures, dimensiones, visuales)
- [ ] Correr Step 8 automatizado y comparar contra tu validación manual
- [ ] Ajustar tolerancias de comparación si es necesario

### Día 12 — Fix edge cases detectados
- [ ] Revisar la tabla de errores de Semana 2
- [ ] Priorizar por frecuencia (arreglar primero los que rompen más QVWs)
- [ ] Aplicar fixes y re-correr los QVWs afectados

### Día 13 — Regression + UI dashboard
- [ ] Re-correr el batch completo (10+ QVWs) en el Streamlit dashboard
- [ ] Verificar que todos los pasos se reportan correctamente en `display_step_selector`
- [ ] Probar "Run Full Pipeline" vs pasos individuales
- [ ] Arreglar bugs de UI residuales (ej. `upload_qvw_stream_to_sharepoint` undefined en [src/app.py:974](src/app.py#L974))

### Día 14 — Documentación + handoff
- [ ] Actualizar `README.md` con los fixes aplicados
- [ ] Documentar troubleshooting (errores comunes + solución)
- [ ] Escribir una guía "cómo añadir un QVW nuevo al pipeline"
- [ ] Exportar métricas finales: % éxito, tiempo promedio por QVW

### Día 15 — Buffer / demo
- [ ] Correr demo end-to-end con stakeholder
- [ ] Recolectar feedback
- [ ] Backlog de mejoras para siguiente iteración

**Criterio de salida semana 3:** pipeline confiable sobre samples, con documentación y tasa de éxito medible.

---

## Riesgos y mitigaciones

| Riesgo | Probabilidad | Mitigación |
|---|---|---|
| `automate_qlikview` no funciona en tu resolución | Alta | Migrar a `locateOnScreen` con imágenes de referencia (Día 3) |
| Azure OpenAI quota/costos altos en Step 5 | Media | Limitar a QVWs pequeños primero; batchear expresiones |
| QVWs muy grandes timeout en DocumentAnalyzer | Media | Filtrar samples por tamaño al inicio |
| DAX generado sintácticamente inválido | Media | Validación post-generación antes de escribir a Power BI |
| Step 6 PDF export via Alt+Tab keypresses es frágil | Alta | Mover lógica a biblioteca Python pura (reportlab) si hay tiempo |
| Perder trabajo por no hacer commits | Baja | Commit diario al final del día |

---

## Checklist de entorno (verificar antes de empezar Día 1)

- [x] `document_analyzer/DocumentAnalyzer_V3.10.qvw` existe
- [x] `data/input_qvw_samples/` tiene QVWs
- [x] `settings.json` apunta a rutas correctas
- [ ] `api_key` y `azure_endpoint` reales configurados (hoy demo)
- [ ] QlikView Personal Edition instalado y licencia aceptada
- [ ] Python 3.11+ con venv creado
- [ ] `pip install -r requirements.txt` sin errores
- [ ] `output/logs/` existe (se crea automáticamente al primer run)
- [ ] Resolución pantalla documentada (`pyautogui.size()`) — afecta Step 1 hasta que se migre a image recognition
