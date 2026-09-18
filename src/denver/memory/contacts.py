"""Denver AI Assistant — Local Contacts & Address Book Subsystem."""

from __future__ import annotations

import csv
import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from denver.logging.logger import get_logger

logger = get_logger("contacts")

DEFAULT_CONTACTS_PATH = Path("data/contacts.json")


@dataclass
class Contact:
    """Represents a single contact in Denver's local address book."""

    name: str
    phone: str = ""
    aliases: list[str] = field(default_factory=list)
    email: str = ""
    relationship: str = ""
    notes: str = ""

    def clean_phone(self) -> str:
        """Return standardized phone number without dashes or spaces."""
        if not self.phone:
            return ""
        cleaned = re.sub(r"[^\d+]", "", self.phone.strip())
        # If starts with +, remove + for WhatsApp URI scheme
        if cleaned.startswith("+"):
            return cleaned[1:]
        return cleaned

    def matches(self, query: str) -> bool:
        """Check if query matches contact name, relationship, or any alias."""
        q = query.strip().lower()
        if not q:
            return False

        clean_name = self.name.lower()
        if q == clean_name or q in clean_name:
            return True

        if self.relationship and q == self.relationship.lower():
            return True

        for alias in self.aliases:
            a = alias.strip().lower()
            if q == a or q in a or a in q:
                return True

        return False

    def to_dict(self) -> dict[str, Any]:
        """Serialize contact to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Contact:
        """Deserialize contact from dictionary."""
        return cls(
            name=str(data.get("name", "")).strip(),
            phone=str(data.get("phone", "")).strip(),
            aliases=[str(a).strip().lower() for a in data.get("aliases", []) if a],
            email=str(data.get("email", "")).strip(),
            relationship=str(data.get("relationship", "")).strip(),
            notes=str(data.get("notes", "")).strip(),
        )


@dataclass
class ContactMatchResult:
    """Outcome of contact query resolution with ambiguity detection."""

    best_match: Contact | None = None
    candidates: list[tuple[Contact, float]] = field(default_factory=list)
    is_ambiguous: bool = False
    confidence: float = 0.0


class ContactBook:
    """Local address book managing contacts stored in data/contacts.json."""

    def __init__(self, file_path: Path | str = DEFAULT_CONTACTS_PATH) -> None:
        self.file_path = Path(file_path)
        self._contacts: list[Contact] = []
        self.load()

    def load(self) -> list[Contact]:
        """Load contacts from JSON file."""
        if not self.file_path.exists():
            self._contacts = self._get_default_contacts()
            self.save()
            return self._contacts

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, list):
                self._contacts = [Contact.from_dict(item) for item in raw if isinstance(item, dict)]
            else:
                self._contacts = []
            logger.info("Loaded %d contacts from %s", len(self._contacts), self.file_path)
        except Exception as exc:
            logger.error("Failed to load contacts from %s: %s", self.file_path, exc)
            self._contacts = []

        return self._contacts

    def save(self) -> bool:
        """Persist contacts to JSON file atomically."""
        try:
            from denver.utils.atomic_write import atomic_write_json
            atomic_write_json(self.file_path, [c.to_dict() for c in self._contacts])
            logger.info("Saved %d contacts to %s", len(self._contacts), self.file_path)
            return True
        except Exception as exc:
            logger.error("Failed to save contacts to %s: %s", self.file_path, exc)
            return False

    def list_all(self) -> list[Contact]:
        """Return all contacts."""
        return list(self._contacts)

    def find_contact_matches(
        self,
        query: str,
        fuzzy_cutoff: float = 0.70,
        ambiguity_delta: float = 0.05,
    ) -> ContactMatchResult:
        """Find contact candidates with confidence scoring and tie/ambiguity detection."""
        import difflib

        q = query.strip()
        if not q:
            return ContactMatchResult()

        q_lower = q.lower()
        raw_digits = re.sub(r"[^\d]", "", q)

        # 0. Check if query is phone-like and matches a stored contact first
        if len(raw_digits) >= 7 and (q.startswith("+") or q.replace("-", "").replace(" ", "").isdigit()):
            for c in self._contacts:
                if c.clean_phone() and (c.clean_phone() == raw_digits or c.phone.replace(" ", "").replace("-", "") == q):
                    return ContactMatchResult(best_match=c, candidates=[(c, 1.0)], is_ambiguous=False, confidence=1.0)
            synthetic = Contact(
                name=q,
                phone=q if q.startswith("+") else f"+{q}",
                aliases=[q, raw_digits],
                relationship="direct_phone",
                notes="Direct dialed phone number",
            )
            return ContactMatchResult(best_match=synthetic, candidates=[(synthetic, 1.0)], is_ambiguous=False, confidence=1.0)

        # Comprehensive relationship synonyms mapping
        rel_synonyms: dict[str, list[str]] = {
            "mom": ["mom", "mother", "amma", "mummy", "maa", "mommy", "mum"],
            "mother": ["mom", "mother", "amma", "mummy", "maa", "mommy", "mum"],
            "amma": ["mom", "mother", "amma", "mummy", "maa", "mommy", "mum"],
            "mummy": ["mom", "mother", "amma", "mummy", "maa", "mommy", "mum"],
            "maa": ["mom", "mother", "amma", "mummy", "maa", "mommy", "mum"],
            "dad": ["dad", "father", "appa", "pappa", "daddy", "pa", "pops", "baba"],
            "father": ["dad", "father", "appa", "pappa", "daddy", "pa", "pops", "baba"],
            "appa": ["dad", "father", "appa", "pappa", "daddy", "pa", "pops", "baba"],
            "pappa": ["dad", "father", "appa", "pappa", "daddy", "pa", "pops", "baba"],
            "daddy": ["dad", "father", "appa", "pappa", "daddy", "pa", "pops", "baba"],
            "brother": ["brother", "bro", "anna", "thambi", "bhai", "bhaiya"],
            "bro": ["brother", "bro", "anna", "thambi", "bhai", "bhaiya"],
            "anna": ["brother", "bro", "anna", "thambi", "bhai", "bhaiya"],
            "bhai": ["brother", "bro", "anna", "thambi", "bhai", "bhaiya"],
            "sister": ["sister", "sis", "akka", "thangachi", "didi", "behen"],
            "sis": ["sister", "sis", "akka", "thangachi", "didi", "behen"],
            "akka": ["sister", "sis", "akka", "thangachi", "didi", "behen"],
            "didi": ["sister", "sis", "akka", "thangachi", "didi", "behen"],
            "wife": ["wife", "spouse", "partner", "wifey"],
            "husband": ["husband", "spouse", "partner", "hubby"],
            "boss": ["boss", "manager", "lead", "supervisor", "team lead"],
            "manager": ["boss", "manager", "lead", "supervisor", "team lead"],
            "friend": ["friend", "buddy", "pal", "bestie", "mate"],
            "son": ["son", "boy", "kid", "child"],
            "daughter": ["daughter", "girl", "kid", "child"],
        }

        # 1. Exact Name or Exact Alias Match (Case-Insensitive)
        exact_matches: list[Contact] = []
        for c in self._contacts:
            if c.name.lower() == q_lower or q_lower in [a.lower() for a in c.aliases]:
                if c not in exact_matches:
                    exact_matches.append(c)

        if len(exact_matches) == 1:
            return ContactMatchResult(best_match=exact_matches[0], candidates=[(exact_matches[0], 1.0)], is_ambiguous=False, confidence=1.0)
        elif len(exact_matches) > 1:
            return ContactMatchResult(best_match=None, candidates=[(c, 1.0) for c in exact_matches], is_ambiguous=True, confidence=1.0)

        # 2. Relationship / Synonym Match (e.g. "father", "mother", "mom", "dad", "boss")
        syns = rel_synonyms.get(q_lower, [q_lower])
        rel_matches: list[Contact] = []
        for c in self._contacts:
            rel = (c.relationship or "").lower()
            if rel and (rel == q_lower or rel in syns or any(s in [a.lower() for a in c.aliases] for s in syns)):
                if c not in rel_matches:
                    rel_matches.append(c)

        if len(rel_matches) == 1:
            return ContactMatchResult(best_match=rel_matches[0], candidates=[(rel_matches[0], 1.0)], is_ambiguous=False, confidence=1.0)
        elif len(rel_matches) > 1:
            return ContactMatchResult(best_match=None, candidates=[(c, 1.0) for c in rel_matches], is_ambiguous=True, confidence=1.0)

        # 3. Exact Phone Match against stored contacts
        if raw_digits and len(raw_digits) >= 4:
            phone_matches: list[Contact] = []
            for c in self._contacts:
                if c.clean_phone() and (c.clean_phone() == raw_digits or c.phone.replace(" ", "").replace("-", "") == q):
                    if c not in phone_matches:
                        phone_matches.append(c)
            if len(phone_matches) == 1:
                return ContactMatchResult(best_match=phone_matches[0], candidates=[(phone_matches[0], 1.0)], is_ambiguous=False, confidence=1.0)
            elif len(phone_matches) > 1:
                return ContactMatchResult(best_match=None, candidates=[(c, 1.0) for c in phone_matches], is_ambiguous=True, confidence=1.0)

        # 4. Multi-token scoring & Fuzzy Match using SequenceMatcher
        scored_candidates: dict[str, tuple[Contact, float]] = {}

        for c in self._contacts:
            # Score against full name
            score = difflib.SequenceMatcher(None, q_lower, c.name.lower()).ratio()

            # Score against individual name tokens (e.g. first name, last name)
            for token in c.name.split():
                token_score = difflib.SequenceMatcher(None, q_lower, token.lower()).ratio()
                score = max(score, token_score)

            # Score against aliases
            for alias in c.aliases:
                alias_score = difflib.SequenceMatcher(None, q_lower, alias.lower()).ratio()
                score = max(score, alias_score)

            # Score against relationship
            if c.relationship:
                rel_score = difflib.SequenceMatcher(None, q_lower, c.relationship.lower()).ratio()
                score = max(score, rel_score)

            # Boost exact prefix matches (e.g. "Alex" matches "Alex Smith" or "Alex Jones")
            for token in c.name.split():
                if token.lower().startswith(q_lower) and len(q_lower) >= 3:
                    prefix_boost = 0.95
                    score = max(score, prefix_boost)

            if score >= fuzzy_cutoff:
                key = f"{c.name}_{c.phone}"
                if key not in scored_candidates or score > scored_candidates[key][1]:
                    scored_candidates[key] = (c, round(score, 4))

        if not scored_candidates:
            # 5. Substring Match Fallback
            for c in self._contacts:
                if c.matches(q_lower):
                    return ContactMatchResult(best_match=c, candidates=[(c, 0.70)], is_ambiguous=False, confidence=0.70)
            return ContactMatchResult()

        sorted_candidates = sorted(scored_candidates.values(), key=lambda x: x[1], reverse=True)
        top_score = sorted_candidates[0][1]

        # Check for ambiguity: any candidates within ambiguity_delta of top_score
        tied_candidates = [item for item in sorted_candidates if (top_score - item[1]) <= ambiguity_delta]

        if len(tied_candidates) > 1:
            logger.info("Found %d ambiguous contact matches for query '%s' (top score: %.2f)", len(tied_candidates), query, top_score)
            return ContactMatchResult(
                best_match=None,
                candidates=tied_candidates,
                is_ambiguous=True,
                confidence=top_score,
            )

        winner = sorted_candidates[0][0]
        logger.info("Matched query '%s' to contact '%s' (score: %.2f)", query, winner.name, top_score)
        return ContactMatchResult(
            best_match=winner,
            candidates=sorted_candidates,
            is_ambiguous=False,
            confidence=top_score,
        )

    def find_contact(self, query: str, fuzzy_cutoff: float = 0.70) -> Contact | None:
        """Find single best contact (returns None if ambiguous)."""
        res = self.find_contact_matches(query, fuzzy_cutoff=fuzzy_cutoff)
        return res.best_match

    def add_or_update(self, contact: Contact) -> None:
        """Add a new contact or update existing contact by name."""
        for idx, existing in enumerate(self._contacts):
            if existing.name.lower() == contact.name.lower():
                self._contacts[idx] = contact
                self.save()
                return

        self._contacts.append(contact)
        self.save()

    def import_from_csv(self, csv_path: str | Path) -> int:
        """Import contacts from Google Contacts or Outlook CSV export."""
        path = Path(csv_path)
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

        imported = 0
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Handle Google Contacts / standard CSV columns
                name = (
                    row.get("Name")
                    or row.get("Full Name")
                    or f"{row.get('First Name', '')} {row.get('Last Name', '')}".strip()
                    or row.get("Given Name", "")
                )
                phone = (
                    row.get("Phone 1 - Value")
                    or row.get("Phone")
                    or row.get("Mobile Phone")
                    or row.get("Primary Phone")
                    or row.get("Phone Number", "")
                )
                email = (
                    row.get("E-mail 1 - Value")
                    or row.get("Email")
                    or row.get("E-mail Address", "")
                )

                if name and phone:
                    contact = Contact(
                        name=name.strip(),
                        phone=phone.strip(),
                        aliases=[name.strip().lower(), name.split()[0].lower()],
                        email=email.strip() if email else "",
                    )
                    self.add_or_update(contact)
                    imported += 1

        self.save()
        logger.info("Successfully imported %d contacts from %s", imported, path)
        return imported

    def _get_default_contacts(self) -> list[Contact]:
        """Initial sample contacts template."""
        return [
            Contact(
                name="Appa",
                phone="+91",
                aliases=["appa", "dad", "father", "pappa"],
                relationship="father",
                notes="Family contact",
            ),
            Contact(
                name="Amma",
                phone="+91",
                aliases=["amma", "mom", "mother"],
                relationship="mother",
                notes="Family contact",
            ),
            Contact(
                name="Prajwal Sindhanur",
                phone="+91",
                aliases=["prajwal", "prajwal sindhanur"],
                relationship="friend",
                notes="Friend",
            ),
        ]


_contact_book_instance: ContactBook | None = None


def get_contact_book(file_path: Path | str = DEFAULT_CONTACTS_PATH) -> ContactBook:
    """Singleton getter for Denver's ContactBook."""
    global _contact_book_instance
    if _contact_book_instance is None:
        _contact_book_instance = ContactBook(file_path=file_path)
    return _contact_book_instance
