from datetime import datetime, timedelta, timezone

import pytest

from video_app.domain.library import (
    FilmBiblePin,
    FilmBiblePinRole,
    FilmBibleSnapshot,
    LibraryAssetBinding,
    LibraryEntity,
    LibraryEntityKind,
    LibraryVersion,
    LibraryVersionKind,
    NameResolutionStatus,
    ReferenceRole,
    ShotBindingRevision,
    resolve_film_bible_name,
)
from video_app.domain.models import DomainValidationError

NOW = datetime(2026, 10, 13, tzinfo=timezone.utc)


def _entity() -> LibraryEntity:
    return LibraryEntity.create(
        entity_id="library_arjun",
        owner_id="owner_a",
        kind=LibraryEntityKind.CHARACTER,
        display_name="Arjun",
        aliases=("అర్జున్",),
        now=NOW,
    )


def _binding() -> LibraryAssetBinding:
    return LibraryAssetBinding(
        asset_id="asset_front",
        asset_version=2,
        asset_sha256="a" * 64,
        role=ReferenceRole.IDENTITY_APPEARANCE,
        view_label="front",
    )


def test_renaming_preserves_opaque_identity_and_unicode_alias_lookup() -> None:
    entity = _entity()

    renamed = entity.rename(
        display_name="Arjun Rao",
        aliases=("అర్జున్", "Arjun"),
        expected_version=1,
        now=NOW + timedelta(seconds=1),
    )

    assert renamed.id == entity.id
    assert renamed.metadata_version == 2
    assert renamed.matches("అర్జు")
    assert renamed.matches("ARJUN")


def test_duplicate_aliases_are_rejected_after_unicode_casefolding() -> None:
    with pytest.raises(DomainValidationError, match="unique"):
        LibraryEntity.create(
            entity_id="library_duplicate",
            owner_id="owner_a",
            kind=LibraryEntityKind.CHARACTER,
            display_name="Arjun",
            aliases=("\uff21\uff32\uff2a\uff35\uff2e",),
            now=NOW,
        )


def test_identity_version_fingerprint_pins_exact_asset_snapshot() -> None:
    entity = _entity()
    first = LibraryVersion.create(
        version_id="version_one",
        entity=entity,
        version_number=1,
        kind=LibraryVersionKind.IDENTITY,
        label="Approved identity",
        notes="Hair and face reference",
        invariants="Hair style",
        state_notes="Neutral",
        voice_profile_id="voice_arjun",
        rights_statement="Permission recorded",
        bindings=(_binding(),),
        now=NOW,
    )
    changed = LibraryVersion.create(
        version_id="version_two",
        entity=entity,
        version_number=1,
        kind=LibraryVersionKind.IDENTITY,
        label="Approved identity",
        notes="Hair and face reference",
        invariants="Hair style",
        state_notes="Neutral",
        voice_profile_id="voice_arjun",
        rights_statement="Permission recorded",
        bindings=(
            LibraryAssetBinding(
                asset_id="asset_front",
                asset_version=3,
                asset_sha256="b" * 64,
                role=ReferenceRole.IDENTITY_APPEARANCE,
                view_label="front",
            ),
        ),
        now=NOW,
    )

    assert first.fingerprint != changed.fingerprint
    assert first.bindings[0].asset_version == 2
    assert first.bindings[0].asset_sha256 == "a" * 64
    approved = first.approve(now=NOW + timedelta(seconds=1))
    assert approved.approved_at == NOW + timedelta(seconds=1)
    assert approved.fingerprint == first.fingerprint


def test_wardrobe_is_separate_from_identity_and_entity_types_are_enforced() -> None:
    wardrobe = LibraryVersion.create(
        version_id="version_wardrobe",
        entity=_entity(),
        version_number=2,
        kind=LibraryVersionKind.WARDROBE,
        label="Blue shirt",
        notes="",
        invariants="Blue cotton shirt",
        state_notes="Story day one",
        voice_profile_id=None,
        rights_statement="",
        bindings=(
            LibraryAssetBinding(
                asset_id="asset_shirt",
                asset_version=1,
                asset_sha256="c" * 64,
                role=ReferenceRole.REVIEW_ONLY,
            ),
        ),
        now=NOW,
    )
    assert wardrobe.kind is LibraryVersionKind.WARDROBE

    with pytest.raises(DomainValidationError, match="incompatible"):
        LibraryVersion.create(
            version_id="version_bad",
            entity=_entity(),
            version_number=3,
            kind=LibraryVersionKind.LOCATION_VIEW,
            label="House exterior",
            notes="",
            invariants="",
            state_notes="",
            voice_profile_id=None,
            rights_statement="",
            bindings=(_binding(),),
            now=NOW,
        )


def _film_bible_pin(
    entity_id: str = "library_arjun", version_id: str = "version_one"
) -> FilmBiblePin:
    return FilmBiblePin(
        entity_id=entity_id,
        library_version_id=version_id,
        library_version_number=1,
        version_kind=LibraryVersionKind.IDENTITY,
        version_fingerprint="d" * 64,
        role=FilmBiblePinRole.CHARACTER_IDENTITY,
    )


def test_film_bible_snapshot_pins_exact_version_and_rename_preserves_resolution() -> None:
    snapshot = FilmBibleSnapshot.create(
        snapshot_id="bible_one",
        project_id="project_one",
        owner_id="owner_a",
        revision=1,
        pins=(_film_bible_pin(),),
        now=NOW,
    ).approve(now=NOW + timedelta(seconds=1))
    renamed = _entity().rename(
        display_name="Arjun Rao",
        aliases=("అర్జున్", "Arjun"),
        expected_version=1,
        now=NOW + timedelta(seconds=2),
    )

    result = resolve_film_bible_name(snapshot, (renamed,), "@అర్జున్")

    assert result.status is NameResolutionStatus.RESOLVED
    assert result.candidates[0].entity_id == "library_arjun"
    assert result.candidates[0].pins[0].library_version_id == "version_one"
    assert snapshot.pins[0].version_fingerprint == "d" * 64


def test_duplicate_alias_is_reported_as_ambiguous_and_missing_name_is_unresolved() -> None:
    second = LibraryEntity.create(
        entity_id="library_second",
        owner_id="owner_a",
        kind=LibraryEntityKind.CHARACTER,
        display_name="Arjun Two",
        aliases=("అర్జున్",),
        now=NOW,
    )
    snapshot = FilmBibleSnapshot.create(
        snapshot_id="bible_two",
        project_id="project_one",
        owner_id="owner_a",
        revision=2,
        pins=(_film_bible_pin(), _film_bible_pin("library_second", "version_second")),
        now=NOW,
    ).approve(now=NOW + timedelta(seconds=1))

    ambiguous = resolve_film_bible_name(snapshot, (_entity(), second), "@అర్జున్")
    missing = resolve_film_bible_name(snapshot, (_entity(), second), "@Sita")

    assert ambiguous.status is NameResolutionStatus.AMBIGUOUS
    assert {item.entity_id for item in ambiguous.candidates} == {
        "library_arjun",
        "library_second",
    }
    assert missing.status is NameResolutionStatus.UNRESOLVED
    assert missing.candidates == ()


def test_shot_binding_revision_fingerprint_changes_only_for_explicit_binding_change() -> None:
    first = ShotBindingRevision.create(
        binding_revision_id="binding_one",
        project_id="project_one",
        owner_id="owner_a",
        shot_id="shot_one",
        shot_version=1,
        revision=1,
        film_bible_snapshot_id="bible_one",
        bindings=(_film_bible_pin(),),
        now=NOW,
    )
    replaced = ShotBindingRevision.create(
        binding_revision_id="binding_two",
        project_id="project_one",
        owner_id="owner_a",
        shot_id="shot_one",
        shot_version=1,
        revision=2,
        film_bible_snapshot_id="bible_two",
        bindings=(_film_bible_pin(version_id="version_two"),),
        now=NOW + timedelta(seconds=1),
    )

    assert first.bindings[0].library_version_id == "version_one"
    assert replaced.bindings[0].library_version_id == "version_two"
    assert first.fingerprint != replaced.fingerprint
