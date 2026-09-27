# Brev setup: handoff for a team member (about 45 minutes, most of it waiting for downloads)

Goal: TradeVoice running on our NVIDIA Brev GPU, reachable on a public https link.
Brev runs the AI brain (LLM) and the photo reader (VLM). Speech-to-text is Intron (cloud), voice replies are Spitch.

## What you need before starting (get these from the AI lead)
- [ ] Access to the team's **Brev account with the credits** (brev.nvidia.com)
- [ ] The **keys**, sent to you privately (NEVER in a group chat, screenshot, or GitHub):
      `INTRON_API_KEY`, `SPITCH_API_KEY`, `NVIDIA_API_KEY`
- [ ] Optional but recommended, for a link that never changes: a free **ngrok** account (ngrok.com) →
      copy the **authtoken** and claim the **free static domain** (Dashboard → Domains)

## Steps
1. **Create the machine** in Brev: GPU **L4 (24 GB)** or **L40S (48 GB)**, disk **100 GB or more**. Open its terminal.
2. **Check the GPU and get the code**
   ```bash
   nvidia-smi
   git clone https://github.com/Godzilla-lab/tradevoice.git && cd tradevoice
   sudo apt-get install -y tmux ffmpeg
   ```
3. **Install (5–10 min)**
   ```bash
   python3 -m venv ~/vllm-env && ~/vllm-env/bin/pip install -U pip vllm
   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
   ```
4. **Create `.env`** with `nano .env` (save: Ctrl+O, Enter, Ctrl+X), filling in the real keys:
   ```
   LOCAL_LLM_URL=http://localhost:8001/v1
   LOCAL_VISION_URL=http://localhost:8002/v1
   LLM_MODELS=local,nvidia/nemotron-3-ultra-550b-a55b,nvidia/nemotron-3-super-120b-a12b
   VISION_MODELS=local,meta/llama-3.2-11b-vision-instruct
   INTRON_API_KEY=...
   SPITCH_API_KEY=...
   NVIDIA_API_KEY=...
   WHATSAPP_TOKEN=...           # Meta → WhatsApp → API Setup → access token
   WHATSAPP_PHONE_ID=...        # Meta → WhatsApp → API Setup → Phone number ID
   WHATSAPP_VERIFY_TOKEN=tradevoice-2026   # any word; type the same in Meta's webhook form
   PUBLIC_URL=https://…         # the app link, so "dashboard" on WhatsApp can send it
   NGROK_AUTHTOKEN=...          # optional
   NGROK_DOMAIN=....ngrok-free.app   # optional
   ```
5. **Demo data + start everything**
   ```bash
   .venv/bin/python seed_demo.py --wipe
   bash start_brev.sh
   ```
   First start downloads the models (5–10 min). It ends with **🟢 TradeVoice is up: https://…**

## Send these back to the AI lead
- [ ] Screenshot of `nvidia-smi` (after step 5, it should show both models using the GPU)
- [ ] The output of the model check at the end of `start_brev.sh`
      (want: "AI brain on our Brev GPU ✅" and "Photo reader on our Brev GPU ✅")
- [ ] The **https link**
- [ ] Screenshot of the Brev console (GPU type, price per hour)

## Quick test on your phone (open the link)
- [ ] Agree and continue → type "Mama Tunde dey owe me forty-five thousand" → tap ✅ Yes
- [ ] Hold 🎤 and say a sale in Pidgin → it answers with a voice note
- [ ] 📎 → photo of a notebook page → lines appear with tick boxes

## If something goes wrong
| Problem | Fix |
|---|---|
| "out of memory" when the photo reader starts (L4) | `bash start_brev.sh stop`, add `VLM_GPU=0.5` and `VLM_LEN=4096` to `.env`, run `bash start_brev.sh` again |
| Error about `--limit-mm-per-prompt` | Tell the AI lead (older vLLM; one-word fix) |
| A part didn't start | `tmux attach -t llm` (or `vision`, `app`, `link`) to see the error; leave with Ctrl+B then D. Send the last 20 lines to the AI lead |
| Mic doesn't work on the phone | The link must start with https:// |

## When finished (credits!)
```bash
bash start_brev.sh stop
```
Then press **Stop** on the machine in the Brev console. Next time: start the machine, `cd tradevoice && bash start_brev.sh`.

## Don'ts
- Don't paste keys or `.env` anywhere; don't `git add .env`.
- Don't leave the machine running overnight (≈ $1–2 per hour).
- Only fake names in the demo (Mama Tunde, Oga Emeka…).
