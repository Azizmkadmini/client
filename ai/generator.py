from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Optional

import httpx

from config import settings
from leads.models import FollowUpStage, Lead
from utils.retry import retry_call


def _sender_profile_block() -> str:
    """
    Construit le bloc expéditeur à partir des settings SENDER_* dans .env.
    Retourné vide si aucun profil n'est configuré.
    """
    name    = getattr(settings, "sender_name",    "").strip()
    tagline = getattr(settings, "sender_tagline", "").strip()
    offers  = getattr(settings, "sender_offers",  "").strip()
    results = getattr(settings, "sender_results", "").strip()
    email   = getattr(settings, "sender_email",   "").strip() or getattr(settings, "smtp_from", "")

    if not name and not tagline:
        return ""

    lines = ["--- SENDER PROFILE ---\n"]
    if name:
        lines.append(f"Name: {name}\n")
    if email:
        lines.append(f"Email: {email}\n")
    if tagline:
        lines.append(f"What I do: {tagline}\n")
    if offers:
        lines.append(f"Services: {offers}\n")
    if results:
        lines.append(f"Typical results: {results}\n")
    lines.append("\n")
    return "".join(lines)


def _render_template(lead: "Lead", stage: "FollowUpStage", extra_context: str) -> tuple[str, str]:
    """
    Rendu basé sur des fichiers templates — zéro IA, résultat toujours propre et professionnel.
    Sélectionne le template selon : catégorie du lead + langue détectée (pays).
    """
    from string import Template

    category = _extract_notes_field(extra_context, "Catégorie") or "default"
    pays     = _extract_notes_field(extra_context, "Pays") or ""
    poste    = _extract_notes_field(extra_context, "Poste") or ""

    fr_countries = {"france", "maroc", "belgique", "tunisie", "suisse", "algérie", "côte d'ivoire"}
    lang = "fr" if pays.strip().lower() in fr_countries else "en"

    # Follow-up : variante différente (ajoute une relance courte)
    if stage.value >= 2:
        category = "default"

    templates_dir = settings.path("templates/email")

    def _pick_variant(base: str) -> Optional[Path]:
        """Retourne un variant numéroté aléatoire (ex: agency_fr_1.txt) ou le fichier de base."""
        numbered = sorted(templates_dir.glob(f"{base}_[0-9]*.txt"))
        if numbered:
            return random.choice(numbered)
        fallback = templates_dir / f"{base}.txt"
        return fallback if fallback.exists() else None

    tpl_path = (
        _pick_variant(f"{category}_{lang}")
        or _pick_variant(f"default_{lang}")
        or _pick_variant("default_en")
    )
    if tpl_path is None:
        return "quick question", "Would you have 15 minutes to discuss how I could help?"

    raw = tpl_path.read_text(encoding="utf-8").strip()

    # Sépare sujet et corps (séparateur ---)
    if "\n---\n" in raw:
        subj_line, body_raw = raw.split("\n---\n", 1)
        subject_tpl = subj_line.replace("subject:", "").strip()
    else:
        subject_tpl = ""
        body_raw = raw

    sender_full = getattr(settings, "sender_name", "").strip() or "Mohamed Aziz Mkadmini"

    # Extrait le prénom du destinataire (premier mot du nom)
    raw_name   = lead.name.strip()
    first_name = raw_name.split()[0].capitalize() if raw_name and not raw_name[0].isdigit() else ""
    # Si le nom est celui de l'entreprise (tout en majuscules ou contient des mots clés), on n'utilise pas de prénom
    prenom = first_name if first_name and len(first_name) > 1 else ""

    # Variables disponibles dans les templates
    vars_map = {
        "nom":        lead.name,
        "prenom":     prenom or lead.name,
        "entreprise": lead.company or lead.name,
        "poste":      poste,
        "sender":     sender_full,
        "email":      getattr(settings, "sender_email", "").strip() or getattr(settings, "smtp_from", ""),
    }

    def safe_render(text: str) -> str:
        # Remplace {clé} par la valeur — ignore les clés inconnues
        result = text
        for key, value in vars_map.items():
            result = result.replace(f"{{{key}}}", value)
        return result

    subject = safe_render(subject_tpl)
    body    = safe_render(body_raw).strip()

    # Pour le follow-up, on ajoute un contexte de relance
    if stage.value == 2:
        relance = (
            "\n\nJe reviens vers vous suite à mon précédent message — ça vaut toujours le coup d'en discuter ?"
            if lang == "fr" else
            "\n\nFollowing up on my previous message — still worth a quick chat?"
        )
        body += relance
    elif stage.value >= 3:
        relance = (
            "\n\nDernier message de ma part — si le timing n'est pas bon, pas de souci, je comprends tout à fait."
            if lang == "fr" else
            "\n\nLast one from me — if the timing isn't right, no worries at all."
        )
        body += relance

    return subject, body


def _clean_subject(subject: str) -> str:
    """
    Nettoie le sujet généré par le modèle :
    - Supprime les préfixes parasites (Re:, Fwd:, Subject:, Curious:...)
    - Tronque à 8 mots max
    - Lowercase sauf noms propres
    """
    import re
    # Supprime préfixes courants
    subject = re.sub(r"(?i)^(re|fwd|subject|curious|question|note)\s*:\s*", "", subject).strip()
    # Supprime guillemets résiduels
    subject = subject.strip('"\'')
    # Tronque à 8 mots
    words = subject.split()
    if len(words) > 8:
        subject = " ".join(words[:8])
    return subject.rstrip(".,?!")


def _extract_notes_field(notes: str, field: str) -> str:
    """Extrait 'Poste : Directeur' → 'Directeur' depuis le champ notes du pipeline."""
    import re
    m = re.search(rf"{re.escape(field)}\s*[:\-]\s*([^|]+)", notes or "")
    return m.group(1).strip() if m else ""


def role_line_hint(poste: str) -> str:
    return f" ({poste})" if poste else ""


# ── Few-shot examples ─────────────────────────────────────────────────────────
# Montrent au modèle EXACTEMENT le format et le ton attendus.

_FEW_SHOT_EXAMPLES_FR = """\
Exemples du format attendu :

[Exemple 1 — Agence marketing]
Les agences qui gèrent plusieurs clients passent souvent des heures à qualifier des prospects manuellement — c'est exactement le problème que je résous avec des systèmes automatisés. Est-ce que vous avez déjà envisagé d'automatiser une partie de votre prospection ?

[Exemple 2 — E-commerce]
La plupart des boutiques en ligne perdent des leads faute d'un système de relance automatique après la première visite. J'aide des e-commerçants à récupérer jusqu'à 30% de ces contacts sans effort manuel — ça vous parlerait d'en discuter 15 minutes ?

[Exemple 3 — SaaS / Tech]
Vous développez un produit SaaS, donc vous savez que chaque heure passée sur la prospection manuelle est une heure de moins sur le produit. J'automatise ce processus de A à Z — est-ce que c'est un sujet prioritaire pour vous en ce moment ?

Maintenant écris un message similaire pour le destinataire ci-dessous :
"""

_FEW_SHOT_EXAMPLES_EN = """\
Examples of the expected format:

[Example 1 — Marketing agency]
Running a marketing agency means your team spends hours on manual prospecting that could be fully automated. I build systems that handle this end-to-end — would that be worth a quick call?

[Example 2 — E-commerce]
Most e-commerce stores leave money on the table because follow-up with new leads is still done manually. I've helped stores recover 30% more leads through automation — is that something you're looking to fix?

[Example 3 — SaaS]
Growing a SaaS product is already a full-time job — adding manual outreach on top slows everything down. I automate lead generation and outreach workflows entirely — would you be open to seeing how it works?

Now write a similar message for the recipient below:
"""


STAGE_HINTS = {
    FollowUpStage.INTRO: (
        "First touch. Mention one specific reason you reached out based on their industry or role. "
        "Soft question at the end. No pitch deck language. Keep it under 3 sentences."
    ),
    FollowUpStage.FOLLOW_UP: (
        "Second message after no reply. Acknowledge they are busy, add one new detail, "
        "keep it shorter than the first message."
    ),
    FollowUpStage.FINAL: (
        "Polite final follow-up. Close the loop, no pressure, leave door open."
    ),
}


class MessageGenerator:
    def __init__(self, history_path: Optional[Path] = None) -> None:
        self.history_path = history_path or settings.path("logs/message_history.jsonl")
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        self._recent_hashes: list[str] = []
        self._load_recent_hashes()

    def generate(
        self,
        lead: Lead,
        stage: FollowUpStage,
        channel: str,
        extra_context: str = "",
    ) -> tuple[str, str]:
        # Templates = ton humain contrôlé. Groq/Ollama produisent souvent du texte générique.
        force_templates = getattr(settings, "email_use_templates_only", True)
        if force_templates or settings.ai_provider.lower() == "template":
            return _render_template(lead, stage, extra_context)

        context = lead.display_context()
        prompt = self._build_prompt(context, stage, channel, extra_context)
        body = self._call_provider(prompt)
        body = self._normalize_body(body)
        subject = ""
        if channel == "email":
            subject = self._generate_subject(context, stage, body, extra_context=extra_context)
        self._remember(body)
        return subject, body

    def _build_prompt(
        self,
        context: dict[str, str],
        stage: FollowUpStage,
        channel: str,
        extra_context: str,
    ) -> str:
        poste    = _extract_notes_field(extra_context, "Poste")
        category = _extract_notes_field(extra_context, "Catégorie")
        pays     = _extract_notes_field(extra_context, "Pays")

        sender_name    = getattr(settings, "sender_name",    "").strip() or "Aziz"
        sender_tagline = getattr(settings, "sender_tagline", "").strip()
        sender_results = getattr(settings, "sender_results", "").strip()

        # Détecte la langue selon le pays (French si France/Maroc/Belgique/Tunisie)
        fr_countries = {"france", "maroc", "belgique", "tunisie", "suisse", "algérie", "côte d'ivoire"}
        use_french = pays.strip().lower() in fr_countries if pays else False

        recipient_line = (
            f"{context['name']}"
            + (f", {poste}" if poste else "")
            + f" chez {context['company']}" if use_french
            else f"{context['name']}"
            + (f", {poste}" if poste else "")
            + f" at {context['company']}"
        )
        industry_hint = (
            f"une agence digitale" if category == "agency" and use_french
            else f"a {category} company" if category and category != "unknown"
            else ""
        )

        if use_french:
            examples = _FEW_SHOT_EXAMPLES_FR
            lang_note = "Réponds UNIQUEMENT en français."
        else:
            examples = _FEW_SHOT_EXAMPLES_EN
            lang_note = "Reply in English only."

        return (
            f"Tu es {sender_name}. {sender_tagline}.\n\n"
            if use_french else
            f"You are {sender_name}. {sender_tagline}.\n\n"
        ) + (
            f"Résultats typiques : {sender_results}\n\n"
            if use_french and sender_results else
            f"Typical results: {sender_results}\n\n"
            if sender_results else ""
        ) + (
            f"Écris le corps d'un email de prospection pour : {recipient_line}"
            + (f" ({industry_hint})" if industry_hint else "") + ".\n"
            if use_french else
            f"Write the body of a cold email to: {recipient_line}"
            + (f" ({industry_hint})" if industry_hint else "") + ".\n"
        ) + (
            f"Étape : {stage.name} — {STAGE_HINTS[stage]}\n\n"
            if use_french else
            f"Stage: {stage.name} — {STAGE_HINTS[stage]}\n\n"
        ) + examples + (
            "\nIMPORTANT :\n"
            "- 2 à 3 phrases maximum\n"
            "- Pas de formule de politesse (pas de Bonjour, pas de Cordialement)\n"
            "- Pas de signature\n"
            "- Pas de 'j'espère que vous allez bien'\n"
            "- Une question directe et précise à la fin\n"
            f"- {lang_note}\n"
            "- Retourne UNIQUEMENT le corps du message\n"
            if use_french else
            "\nIMPORTANT:\n"
            "- 2 to 3 sentences max\n"
            "- No greeting (no Hi, no Dear)\n"
            "- No sign-off, no signature\n"
            "- No 'I hope this email finds you well'\n"
            "- End with one direct, specific question\n"
            f"- {lang_note}\n"
            "- Return ONLY the email body\n"
        )

    def _call_provider(self, prompt: str) -> str:
        provider = settings.ai_provider.lower()
        if provider == "openai":
            return retry_call(lambda: self._call_openai(prompt))
        if provider == "groq":
            return retry_call(lambda: self._call_groq(prompt))
        return retry_call(lambda: self._call_ollama(prompt))

    def _call_ollama(self, prompt: str) -> str:
        url = f"{settings.ollama_base_url.rstrip('/')}/api/generate"
        payload = {
            "model": settings.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.9, "top_p": 0.9},
        }
        with httpx.Client(timeout=120.0) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
        text = (data.get("response") or "").strip()
        if not text:
            raise RuntimeError("Ollama returned an empty message")
        return text

    def _call_groq(self, prompt: str) -> str:
        """Groq — gratuit, 14 400 req/jour, Llama-3.3-70B."""
        groq_key = getattr(settings, "groq_api_key", "").strip()
        if not groq_key:
            raise RuntimeError("GROQ_API_KEY non configuré dans .env")
        groq_model = getattr(settings, "groq_model", "llama-3.3-70b-versatile").strip()
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}"},
                json={
                    "model": groq_model,
                    "temperature": 0.8,
                    "max_tokens": 250,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You write short, genuine cold outreach messages that feel like they came from a real person.\n"
                                "STRICT RULES:\n"
                                "- Under 100 words\n"
                                "- No greeting, no sign-off, no signature\n"
                                "- No exclamation marks\n"
                                "- No words: free, guaranteed, urgent, limited time, revolutionary, "
                                "  optimize, leverage, synergy, game-changer, end-to-end, seamless\n"
                                "- No links, no emojis\n"
                                "- Plain text only\n"
                                "- End with one soft question"
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                },
            )
            response.raise_for_status()
            text = (response.json()["choices"][0]["message"]["content"] or "").strip()
        if not text:
            raise RuntimeError("Groq returned an empty message")
        return text

    def _call_openai(self, prompt: str) -> str:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        completion = client.chat.completions.create(
            model=settings.openai_model,
            temperature=0.9,
            messages=[
                {
                    "role": "system",
                    "content": "You write concise, human outreach copy.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        text = (completion.choices[0].message.content or "").strip()
        if not text:
            raise RuntimeError("OpenAI returned an empty message")
        return text

    def _generate_subject(
        self,
        context: dict[str, str],
        stage: FollowUpStage,
        body: str,
        extra_context: str = "",
    ) -> str:
        poste    = _extract_notes_field(extra_context, "Poste")
        category = _extract_notes_field(extra_context, "Catégorie")

        industry_hint = f" in {category}" if category else ""
        role_hint     = role_line_hint(poste)

        pays = _extract_notes_field(extra_context, "Pays")
        fr_countries = {"france", "maroc", "belgique", "tunisie", "suisse", "algérie"}
        use_french = pays.strip().lower() in fr_countries if pays else False

        if use_french:
            prompt = (
                "Écris UN objet d'email. RÈGLES STRICTES :\n"
                "- Maximum 6 mots\n"
                "- Minuscules sauf noms propres\n"
                "- Mots interdits : 'collaboration', 'partenariat', 'opportunité', 'proposition'\n"
                "- Doit sembler écrit par un humain, pas par un commercial\n"
                "- Orienté bénéfice ou curiosité\n"
                "- EN FRANÇAIS\n"
                f"Destinataire : {context['name']}{role_hint} chez {context['company']}{industry_hint}.\n"
                f"Aperçu de l'email : {body[:120]}\n"
                "Retourne UNIQUEMENT l'objet. Pas de guillemets. Pas de ponctuation à la fin."
            )
        else:
            prompt = (
                "Write one email subject line. STRICT RULES:\n"
                "- Maximum 6 words\n"
                "- Lowercase except proper nouns\n"
                "- No words: 'collaboration', 'partnership', 'opportunity', 'proposal', 'innovative'\n"
                "- Must feel like a human sent it (not marketing)\n"
                "- Curiosity-driven or benefit-specific\n"
                f"Recipient: {context['name']}{role_hint} at {context['company']}{industry_hint}.\n"
                f"Email preview: {body[:120]}\n"
                "Return ONLY the subject line. No quotes. No punctuation at the end."
            )
        subject = self._call_provider(prompt).strip().strip('"').rstrip(".")
        subject = _clean_subject(subject)
        return subject[:120] or f"quick question for {context['name']}"

    def _normalize_body(self, text: str) -> str:
        import re
        text = text.strip()
        # Supprime "Subject: ..." si le modèle l'a inclus par erreur
        text = re.sub(r"(?i)^subject\s*:[^\n]*\n?", "", text)
        # Supprime toute ligne de salutation en début (Dear X, / Hello X Y,)
        text = re.sub(r"(?i)^(dear|hello|hi|bonjour|salut|hey)\s+[\w\s]{1,40}[,.]?\s*", "", text)
        # Supprime les signatures en fin (Best, Aziz / Regards, / Cordialement...)
        text = re.sub(
            r"(?i)\s*(best(?: regards)?|regards|sincerely|cheers|cordialement|"
            r"kind regards|warm regards|yours truly|à bientôt|bien cordialement)"
            r"[,.]?\s*\n?.*$",
            "",
            text,
            flags=re.DOTALL,
        )
        cleaned = " ".join(text.strip().replace("\r", "\n").split())
        # Supprime guillemets encadrants si le modèle les a ajoutés
        cleaned = cleaned.strip('"\'')
        if len(cleaned) > 500:
            cleaned = cleaned[:497].rstrip() + "..."
        return cleaned

    def _hash_message(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _load_recent_hashes(self) -> None:
        if not self.history_path.exists():
            return
        lines = self.history_path.read_text(encoding="utf-8").splitlines()[-50:]
        for line in lines:
            try:
                record = json.loads(line)
                self._recent_hashes.append(record["hash"])
            except (json.JSONDecodeError, KeyError):
                continue

    def _remember(self, text: str) -> None:
        digest = self._hash_message(text)
        attempts = 0
        while digest in self._recent_hashes[-10:] and attempts < 3:
            text = f"{text.rstrip('.')} — just wanted to reach out personally."
            digest = self._hash_message(text)
            attempts += 1
        record = {"hash": digest, "preview": text[:160]}
        with self.history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
        self._recent_hashes.append(digest)

    def ensure_not_duplicate(self, text: str) -> bool:
        digest = self._hash_message(text)
        return digest not in self._recent_hashes[-10:]
