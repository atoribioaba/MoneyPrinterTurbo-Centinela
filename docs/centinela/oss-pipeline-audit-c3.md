# AUDITORÍA OPEN SOURCE DEL PIPELINE — C3

Estado: **EN CURSO / NO AUTORIZA F58**

Fecha: 2026-08-30

Esta auditoría separa licencia de código, licencia de pesos/servicio y validación de recursos en el hardware objetivo. Una fila no cuenta como verificada para F58 mientras tenga campos críticos `NO VERIFICADO`.

| Función | Actual | Mejor candidato OSS | Gratuito | Licencia | VRAM/RAM | Mejora | Decisión |
|---|---|---|---|---|---|---|---|
| Runtime LLM local | Ollama | Ollama; llama.cpp como fallback/control | Sí | Ollama MIT; llama.cpp MIT | Ollama+Qwen3.5 ya probado localmente; medición final tras reconciliación | Mantiene UX simple; llama.cpp aporta control fino/portabilidad | **MANTENER** Ollama; **PRUEBA A/B** llama.cpp sólo si mejora estabilidad/VRAM |
| LLM principal | Qwen3.5 4B Q4_K_M | Qwen3.5-4B | Sí | Apache-2.0 | Prueba local previa ~5.5 GiB VRAM con configuración actual; recertificar tras reconciliación | Buen ajuste frente a modelos mayores para RTX 2060 6 GB | **MANTENER** |
| TTS local | Qwen3-TTS | Qwen3-TTS 0.6B/1.7B según calidad/VRAM | Sí | Código Apache-2.0; pesos oficiales Apache-2.0 | **NO VERIFICADO FINAL** en RTX 2060 tras reconciliación | Español soportado; local; control de voz | **MANTENER / PRUEBA A/B** 0.6B vs variante vigente; no descargar nuevos GB sin autorización |
| TTS online fallback | edge-tts / posible integración MPT | Qwen3-TTS local como principal; edge-tts sólo fallback | Cliente gratuito; servicio online | cliente edge-tts LGPLv3 (SRT composer MIT); servicio Microsoft no es OSS/local | VRAM 0; requiere red | Timestamps/SRT prácticos, pero pierde privacidad/localidad y depende de servicio externo | **NO COMPENSA como principal**; fallback opcional |
| STT / alignment | faster-whisper + Whisper | faster-whisper | Sí | faster-whisper MIT; Whisper código y pesos MIT | **PENDIENTE medición** modelo elegido en RTX 2060 | Buen rendimiento CTranslate2; usar sólo cuando timestamps TTS no basten | **MANTENER** |
| Video / composición | FFmpeg + renderer Centinela | FFmpeg | Sí | LGPL-2.1+ por defecto; puede pasar a GPL-2+ según build | CPU/libx264; NVENC usa GPU; medición local pendiente | Es estándar, estable y ya integrado | **MANTENER**; verificar `ffmpeg -L/-buildconf` local |
| Encoding GPU | h264_nvenc | FFmpeg h264_nvenc con libx264 fallback | Sí, sujeto a driver NVIDIA | Licencia efectiva depende del build FFmpeg; **NO VERIFICADA LOCAL** | RTX 2060 6 GB; medición real pendiente | Acelera render sin eliminar fallback CPU | **MANTENER**, condicionado a smoke real NVENC |
| Matching semántico guion→clip | CLIP/SemanticMatcher | OpenCLIP | Sí | OpenCLIP MIT; pesos concretos deben verificarse por model card | Depende del backbone; **NO FIJAR modelo mayor sin prueba 6 GB** | Mejor ecosistema OSS y modelos intercambiables | **ALTERNATIVA OSS RECOMENDADA / PRUEBA A/B** |
| Grounding espacial | Florence-2 | Florence-2-base | Sí | MIT | **NO VERIFICADO LOCAL**; usar después de MaterialSelector | Complementa CLIP con grounding/ubicación, no sustituye autoridad de selección | **PRUEBA A/B**, mantener como apoyo |
| Mejora imagen/vídeo | No canónico | Real-ESRGAN | Sí | BSD-3-Clause para código; verificar pesos concretos antes de fijar | **NO VERIFICADO LOCAL** en 6 GB | Puede ayudar en material de baja resolución, pero puede inventar textura y degradar rigor astronómico | **PRUEBA A/B**, nunca por defecto |
| Música generativa | No canónico | AudioCraft/MusicGen como referencia de investigación | Código sí; pesos abiertos no comerciales | Código MIT; pesos MusicGen CC-BY-NC-4.0 | Documentación oficial indica >=16 GB GPU para modelos medium; fuera de objetivo RTX 2060 | No encaja en 6 GB ni en posible uso comercial/monetizable | **NO COMPENSA** para producción |
| Scientific Visuals | Renderer determinista Centinela | Mantener renderer determinista + FFmpeg/Pillow | Sí | Dependencias OSS; inventario final pendiente | Ligero; medición final pendiente | Trazable a FactLock, determinista, sin IA generativa | **MANTENER** |
| Automatización / entorno | Git + uv + Python + GitHub Actions para CI | Windows nativo + uv; Actions sólo CI | Sí | Licencias de herramientas a inventariar en cierre | PC objetivo ya definido; medición no crítica para runtime | Reproducibilidad sin imponer Docker/WSL2 | **MANTENER** |

## Clasificación

- Qwen3.5: **PESOS ABIERTOS + Apache-2.0**.
- Qwen3-TTS: **OPEN SOURCE / PESOS ABIERTOS + Apache-2.0** según repos/model cards oficiales consultados.
- Ollama / llama.cpp / faster-whisper / OpenCLIP / Florence-2 / Real-ESRGAN: **OPEN SOURCE + 100 % GRATUITA** en código; los pesos concretos, cuando apliquen, deben conservar su propia licencia/model card.
- edge-tts: cliente OSS pero servicio TTS externo; clasificar operativamente como **OSS CON SERVICIO EXTERNO**.
- MusicGen: código OSS MIT + pesos CC-BY-NC-4.0: **OSS CON PESOS NO COMERCIALES**; no candidato de producción.
- FFmpeg: **OPEN SOURCE + 100 % GRATUITA**, pero la licencia efectiva del binario local depende de su configuración (`LGPL`/`GPL`) y se debe verificar en el PC.

## Fuentes oficiales verificadas

- MoneyPrinterTurbo requirements: https://github.com/harry0703/MoneyPrinterTurbo/blob/main/requirements.txt
- Ollama: https://github.com/ollama/ollama/blob/main/LICENSE
- llama.cpp: https://github.com/ggml-org/llama.cpp/blob/master/LICENSE
- Qwen3.5-4B: https://huggingface.co/Qwen/Qwen3.5-4B
- Qwen3-TTS código: https://github.com/QwenLM/Qwen3-TTS
- Qwen3-TTS 1.7B CustomVoice: https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice
- Qwen3-TTS 0.6B Base: https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base
- faster-whisper: https://github.com/SYSTRAN/faster-whisper/blob/master/LICENSE
- Whisper: https://github.com/openai/whisper
- edge-tts: https://github.com/rany2/edge-tts
- FFmpeg license: https://ffmpeg.org/doxygen/trunk/md_LICENSE.html
- OpenCLIP: https://github.com/mlfoundations/open_clip
- Florence-2-base: https://huggingface.co/microsoft/Florence-2-base
- Real-ESRGAN: https://github.com/xinntao/Real-ESRGAN
- AudioCraft/MusicGen: https://github.com/facebookresearch/audiocraft

## Bloqueos para marcar la auditoría como completa en F58

1. Verificar licencia/configuración del **binario FFmpeg real** del PC.
2. Medir Qwen3-TTS real (modelo exacto), RAM, VRAM, tiempo y estabilidad.
3. Medir faster-whisper con el modelo finalmente elegido.
4. Fijar, si se usa, el modelo OpenCLIP exacto y verificar la licencia de sus pesos.
5. Fijar, si se usa, Florence-2 exacto y medir memoria/latencia local.
6. Si Real-ESRGAN entra en V1, verificar pesos concretos y prueba A/B de fidelidad astronómica; si no aporta, dejarlo fuera.
7. Resolver música/SFX con licencia de producción demostrable; MusicGen queda descartado como candidato principal por pesos CC-BY-NC y requisitos de GPU.
8. Generar inventario/SBOM final de dependencias del entorno V1 reconciliado.

Hasta completar estos puntos: `OSS_AUDIT_COMPLETE=FALSE` y `ARCHITECTURE_FREEZE_AUTHORIZED=FALSE`.
