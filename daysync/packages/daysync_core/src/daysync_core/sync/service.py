from __future__ import annotations

from difflib import SequenceMatcher
import json
import sqlite3
from statistics import median

from daysync_core.errors import DaySyncError
from daysync_core.utils import new_uuid, utc_now_iso

AUTO_PASS_MIN_CANDIDATE_MARGIN = 0.1
AUTO_CONFORM_MAX_SEEDS_PER_MEDIA = 2
AUTO_CONFORM_MIN_TEXT_LENGTH = 4


def create_manual_anchor_sync(
    connection: sqlite3.Connection,
    project_id: str,
    video_subtitle_id: str,
    audio_subtitle_id: str,
) -> dict[str, object]:
    video_anchor = _load_project_subtitle(connection, project_id, video_subtitle_id)
    audio_anchor = _load_project_subtitle(connection, project_id, audio_subtitle_id)
    if video_anchor["track_type"] != "video_ref" or audio_anchor["track_type"] != "external_audio":
        raise DaySyncError("ANCHOR_SUBTITLE_INVALID", "Selected anchor subtitle is invalid")
    if video_anchor["source_start_ms"] is None or audio_anchor["source_start_ms"] is None:
        raise DaySyncError(
            "ANCHOR_SUBTITLE_INVALID",
            "Selected subtitles do not have mapped source times",
        )
    now = utc_now_iso()
    track_offset_ms = audio_anchor["flat_start_ms"] - video_anchor["flat_start_ms"]
    video_items = _load_flat_timeline_items(connection, video_anchor["flat_timeline_id"])
    audio_items = _load_flat_timeline_items(connection, audio_anchor["flat_timeline_id"])
    sync_results = _build_track_sync_results(
        project_id=project_id,
        video_anchor=video_anchor,
        audio_anchor=audio_anchor,
        video_items=video_items,
        audio_items=audio_items,
        track_offset_ms=track_offset_ms,
        created_at=now,
    )
    if not sync_results:
        raise DaySyncError("ANCHOR_SUBTITLE_INVALID", "Selected anchor pair does not produce any overlapping track segment")

    _clear_existing_manual_sync_results(connection, project_id, sync_results)
    for sync_result in sync_results:
        connection.execute(
            """
            INSERT INTO sync_results (
              id, project_id, session_id, video_media_file_id, audio_media_file_id, video_in_ms, video_out_ms,
              audio_in_ms, audio_out_ms, offset_ms, drift_ppm, confidence_score, status, source,
              video_anchor_subtitle_id, audio_anchor_subtitle_id, confidence_breakdown_json, created_at, updated_at
            )
            VALUES (:id, :project_id, :session_id, :video_media_file_id, :audio_media_file_id, :video_in_ms,
                    :video_out_ms, :audio_in_ms, :audio_out_ms, :offset_ms, :drift_ppm, :confidence_score,
                    :status, :source, :video_anchor_subtitle_id, :audio_anchor_subtitle_id,
                    :confidence_breakdown_json, :created_at, :updated_at)
            """,
            sync_result,
        )
    connection.commit()
    representative_sync = next(
        (
            item
            for item in sync_results
            if item["video_media_file_id"] == video_anchor["source_media_file_id"]
            and item["audio_media_file_id"] == audio_anchor["source_media_file_id"]
        ),
        sync_results[0],
    )
    return {
        "sync_result": representative_sync,
        "generated_count": len(sync_results),
        "track_offset_ms": track_offset_ms,
    }


def preview_auto_conform(
    connection: sqlite3.Connection,
    project_id: str,
    context_radius: int = 2,
    min_anchor_count: int = 3,
    tolerance_ms: int = 500,
    min_inlier_ratio: float = 0.6,
) -> dict[str, object]:
    video_rows = _load_project_subtitles_by_track_type(connection, project_id, "video_ref")
    audio_rows = _load_project_subtitles_by_track_type(connection, project_id, "external_audio")
    if not video_rows or not audio_rows:
        return _empty_auto_conform_preview(
            reason="missing_subtitle_tracks",
            selected_seed_count=0,
            eligible_seed_count=0,
        )

    selected_seeds, excluded_seeds = _select_auto_conform_seeds(video_rows)
    anchor_pairs: list[dict[str, object]] = []
    seen_audio_hits: set[tuple[str | None, int | None]] = set()

    for seed in selected_seeds:
        recommendation = _recommend_auto_candidates_internal(
            connection,
            project_id,
            str(seed["id"]),
            context_radius=context_radius,
        )
        chosen_candidate: dict[str, object] | None = None
        chosen_reason = "no_viable_audio_candidate"
        for candidate in recommendation["candidates"]:
            candidate_reason = _auto_conform_candidate_rejection_reason(candidate)
            if candidate_reason is not None:
                chosen_reason = candidate_reason
                continue
            audio_hit_key = (
                str(candidate.get("source_media_file_id")) if candidate.get("source_media_file_id") else None,
                int(candidate["source_start_ms"]) if candidate.get("source_start_ms") is not None else None,
            )
            if audio_hit_key in seen_audio_hits:
                chosen_reason = "duplicate_audio_anchor"
                continue
            chosen_candidate = candidate
            seen_audio_hits.add(audio_hit_key)
            break

        if chosen_candidate is None:
            excluded_seeds.append(
                {
                    "subtitle_id": str(seed["id"]),
                    "raw_text": str(seed["raw_text"]),
                    "source_filename": seed["source_filename"],
                    "reason": chosen_reason,
                }
            )
            continue

        anchor_pairs.append(
            {
                "video_subtitle_id": str(seed["id"]),
                "video_text": str(seed["raw_text"]),
                "video_source_media_file_id": seed["source_media_file_id"],
                "video_source_filename": seed["source_filename"],
                "video_source_start_ms": seed["source_start_ms"],
                "video_flat_start_ms": seed["flat_start_ms"],
                "audio_subtitle_id": str(chosen_candidate["subtitle_id"]),
                "audio_text": str(chosen_candidate["raw_text"]),
                "audio_source_media_file_id": chosen_candidate["source_media_file_id"],
                "audio_source_filename": chosen_candidate["source_filename"],
                "audio_source_start_ms": chosen_candidate["source_start_ms"],
                "audio_flat_start_ms": chosen_candidate["flat_start_ms"],
                "offset_ms": int(chosen_candidate["flat_start_ms"]) - int(seed["flat_start_ms"]),
                "source_offset_ms": int(chosen_candidate["source_start_ms"]) - int(seed["source_start_ms"]),
                "text_similarity": float(chosen_candidate["text_similarity"]),
                "context_similarity": float(chosen_candidate["context_similarity"]),
                "final_score": float(chosen_candidate["final_score"]),
                "candidate_margin": float(chosen_candidate["candidate_margin"]),
                "reverse_margin": float(chosen_candidate["reverse_margin"]),
                "reverse_match_consistent": bool(chosen_candidate["reverse_match_consistent"]),
                "negative_evidence_count": int(chosen_candidate["negative_evidence_count"]),
                "mapping_warning": chosen_candidate["mapping_warning"],
            }
        )

    cluster_analysis = _analyze_auto_conform_pairs(
        anchor_pairs,
        tolerance_ms=tolerance_ms,
        min_inlier_ratio=min_inlier_ratio,
        min_anchor_count=min_anchor_count,
    )
    representative_pair = cluster_analysis["representative_pair"]
    preview_offset_ms = cluster_analysis["cluster_summary"]["final_offset_ms"]
    if preview_offset_ms is None and cluster_analysis["cluster_summary"]["candidate_count"] > 0:
        preview_offset_ms = cluster_analysis["cluster_summary"]["median_offset_ms"]

    preview_segments: list[dict[str, object]] = []
    if representative_pair is not None and preview_offset_ms is not None:
        preview_segments = _build_auto_conform_preview_segments(
            connection,
            project_id,
            representative_video_subtitle_id=str(representative_pair["video_subtitle_id"]),
            representative_audio_subtitle_id=str(representative_pair["audio_subtitle_id"]),
            track_offset_ms=int(preview_offset_ms),
            confidence_score=max(float(cluster_analysis["auto_accept_decision"]["average_candidate_margin"]), 0.5),
        )

    return {
        "representative_pair": representative_pair,
        "anchor_pairs": cluster_analysis["anchor_pairs"],
        "excluded_seeds": excluded_seeds,
        "cluster_summary": cluster_analysis["cluster_summary"],
        "auto_accept_decision": cluster_analysis["auto_accept_decision"],
        "preview_segments": preview_segments,
        "ready_to_apply": bool(representative_pair is not None and preview_segments),
        "selected_seed_count": len(selected_seeds),
        "eligible_seed_count": len(anchor_pairs),
    }


def apply_auto_conform(
    connection: sqlite3.Connection,
    project_id: str,
    offset_ms: int,
    representative_video_subtitle_id: str,
    representative_audio_subtitle_id: str,
) -> dict[str, object]:
    preview = preview_auto_conform(connection, project_id)
    representative_pair = preview["representative_pair"]
    if representative_pair is None:
        raise DaySyncError("ANCHOR_SUBTITLE_INVALID", "当前没有可应用的自动整日合板提案")

    preview_offset = preview["cluster_summary"]["final_offset_ms"]
    if preview_offset is None:
        preview_offset = preview["cluster_summary"]["median_offset_ms"]

    if (
        str(representative_pair["video_subtitle_id"]) != representative_video_subtitle_id
        or str(representative_pair["audio_subtitle_id"]) != representative_audio_subtitle_id
    ):
        raise DaySyncError("ANCHOR_SUBTITLE_INVALID", "自动整日合板提案已变化，请重新预览后再应用")
    if preview_offset is None:
        raise DaySyncError("ANCHOR_SUBTITLE_INVALID", "自动整日合板提案未产出可用 offset")

    video_anchor = _load_project_subtitle(connection, project_id, representative_video_subtitle_id)
    audio_anchor = _load_project_subtitle(connection, project_id, representative_audio_subtitle_id)
    video_items = _load_flat_timeline_items(connection, video_anchor["flat_timeline_id"])
    audio_items = _load_flat_timeline_items(connection, audio_anchor["flat_timeline_id"])
    auto_accept_eligible = bool(preview["auto_accept_decision"]["eligible"]) and int(preview_offset) == int(offset_ms)
    status = "accepted_auto" if auto_accept_eligible else "accepted_manual"
    confidence_breakdown = {
        "auto_conform": True,
        "track_sync": True,
        "track_offset_ms": offset_ms,
        "preview_cluster_summary": preview["cluster_summary"],
        "preview_auto_accept_decision": preview["auto_accept_decision"],
        "confirmed_by_user": not auto_accept_eligible,
    }
    created_at = utc_now_iso()
    sync_results = _build_track_sync_results(
        project_id=project_id,
        video_anchor=video_anchor,
        audio_anchor=audio_anchor,
        video_items=video_items,
        audio_items=audio_items,
        track_offset_ms=offset_ms,
        created_at=created_at,
        status=status,
        source="auto_text",
        confidence_score=1.0 if auto_accept_eligible else 0.85,
        confidence_breakdown=confidence_breakdown,
    )
    if not sync_results:
        raise DaySyncError("ANCHOR_SUBTITLE_INVALID", "当前 offset 无法生成整日自动合板片段")

    _clear_existing_auto_sync_results(connection, project_id)
    for sync_result in sync_results:
        connection.execute(
            """
            INSERT INTO sync_results (
              id, project_id, session_id, video_media_file_id, audio_media_file_id, video_in_ms, video_out_ms,
              audio_in_ms, audio_out_ms, offset_ms, drift_ppm, confidence_score, status, source,
              video_anchor_subtitle_id, audio_anchor_subtitle_id, confidence_breakdown_json, created_at, updated_at
            )
            VALUES (:id, :project_id, :session_id, :video_media_file_id, :audio_media_file_id, :video_in_ms,
                    :video_out_ms, :audio_in_ms, :audio_out_ms, :offset_ms, :drift_ppm, :confidence_score,
                    :status, :source, :video_anchor_subtitle_id, :audio_anchor_subtitle_id,
                    :confidence_breakdown_json, :created_at, :updated_at)
            """,
            sync_result,
        )
    connection.commit()

    representative_sync = next(
        (
            item
            for item in sync_results
            if item["video_media_file_id"] == video_anchor["source_media_file_id"]
            and item["audio_media_file_id"] == audio_anchor["source_media_file_id"]
        ),
        sync_results[0],
    )
    return {
        "sync_result": representative_sync,
        "generated_count": len(sync_results),
        "track_offset_ms": offset_ms,
        "sync_result_summary": {
            "status": status,
            "source": "auto_text",
            "accepted_count": len(sync_results),
            "representative_video_file": representative_sync["video_file"],
            "representative_audio_file": representative_sync["audio_file"],
        },
    }


def list_sync_results(connection: sqlite3.Connection, project_id: str) -> list[dict[str, object]]:
    rows = connection.execute(
        """
        SELECT sr.id, sr.project_id, sr.video_media_file_id, sr.audio_media_file_id, sr.video_in_ms,
               sr.video_out_ms, sr.audio_in_ms, sr.audio_out_ms, sr.offset_ms, sr.confidence_score,
               sr.status, sr.source, sr.video_anchor_subtitle_id, sr.audio_anchor_subtitle_id,
               sr.confidence_breakdown_json, sr.created_at, sr.updated_at,
               vm.filename AS video_file, am.filename AS audio_file,
               vs.raw_text AS video_anchor_text, aus.raw_text AS audio_anchor_text
        FROM sync_results sr
        JOIN media_files vm ON vm.id = sr.video_media_file_id
        JOIN media_files am ON am.id = sr.audio_media_file_id
        LEFT JOIN subtitles vs ON vs.id = sr.video_anchor_subtitle_id
        LEFT JOIN subtitles aus ON aus.id = sr.audio_anchor_subtitle_id
        WHERE sr.project_id = ?
        ORDER BY sr.created_at DESC
        """,
        (project_id,),
    ).fetchall()
    if not rows:
        return []

    sync_result_ids = [row["id"] for row in rows]
    review_events = connection.execute(
        """
        SELECT id, sync_result_id, event_type, old_offset_ms, new_offset_ms, note, created_at
        FROM review_events
        WHERE sync_result_id IN ({placeholders})
        ORDER BY created_at DESC
        """.format(placeholders=",".join("?" for _ in sync_result_ids)),
        sync_result_ids,
    ).fetchall()
    review_events_by_result: dict[str, list[dict[str, object]]] = {}
    for event in review_events:
        review_events_by_result.setdefault(event["sync_result_id"], []).append(dict(event))

    results: list[dict[str, object]] = []
    for row in rows:
        item = dict(row)
        item["confidence_breakdown"] = _parse_json(item.pop("confidence_breakdown_json"))
        item["review_events"] = review_events_by_result.get(item["id"], [])
        results.append(item)
    return results


def list_review_queue(connection: sqlite3.Connection, project_id: str) -> list[dict[str, object]]:
    rows = connection.execute(
        """
        SELECT sr.id, sr.project_id, sr.video_media_file_id, sr.audio_media_file_id, sr.video_in_ms,
               sr.video_out_ms, sr.audio_in_ms, sr.audio_out_ms, sr.offset_ms, sr.confidence_score,
               sr.status, sr.source, sr.video_anchor_subtitle_id, sr.audio_anchor_subtitle_id,
               sr.confidence_breakdown_json, sr.created_at, sr.updated_at,
               vm.filename AS video_file, am.filename AS audio_file,
               vs.raw_text AS video_anchor_text, aus.raw_text AS audio_anchor_text
        FROM sync_results sr
        JOIN media_files vm ON vm.id = sr.video_media_file_id
        JOIN media_files am ON am.id = sr.audio_media_file_id
        LEFT JOIN subtitles vs ON vs.id = sr.video_anchor_subtitle_id
        LEFT JOIN subtitles aus ON aus.id = sr.audio_anchor_subtitle_id
        WHERE sr.project_id = ?
          AND sr.status IN ('candidate', 'needs_review')
        ORDER BY sr.created_at DESC
        """,
        (project_id,),
    ).fetchall()

    if not rows:
        return []

    sync_result_ids = [row["id"] for row in rows]
    review_events = connection.execute(
        """
        SELECT id, sync_result_id, event_type, old_offset_ms, new_offset_ms, note, created_at
        FROM review_events
        WHERE sync_result_id IN ({placeholders})
        ORDER BY created_at DESC
        """.format(placeholders=",".join("?" for _ in sync_result_ids)),
        sync_result_ids,
    ).fetchall()
    review_events_by_result: dict[str, list[dict[str, object]]] = {}
    for event in review_events:
        review_events_by_result.setdefault(event["sync_result_id"], []).append(dict(event))

    queue_items: list[dict[str, object]] = []
    for row in rows:
        item = dict(row)
        item["confidence_breakdown"] = _parse_json(item.pop("confidence_breakdown_json"))
        item["review_events"] = review_events_by_result.get(item["id"], [])
        queue_items.append(item)
    return queue_items


def recommend_auto_candidates(
    connection: sqlite3.Connection,
    project_id: str,
    anchor_subtitle_id: str,
    limit: int = 5,
    context_radius: int = 1,
) -> dict[str, object]:
    recommendation = _recommend_auto_candidates_internal(
        connection,
        project_id,
        anchor_subtitle_id,
        context_radius=context_radius,
    )
    return {
        **recommendation,
        "limit": limit,
        "candidates": recommendation["candidates"][:limit],
    }


def create_cluster_sync_candidate(
    connection: sqlite3.Connection,
    project_id: str,
    pairs: list[dict[str, str]],
    tolerance_ms: int = 500,
    min_inlier_ratio: float = 0.6,
    min_anchor_count: int = 3,
    context_radius: int = 1,
    note: str | None = None,
) -> dict[str, object]:
    analysis = analyze_offset_cluster(
        connection,
        project_id,
        pairs,
        tolerance_ms=tolerance_ms,
        min_inlier_ratio=min_inlier_ratio,
        min_anchor_count=min_anchor_count,
        context_radius=context_radius,
    )
    pair_analyses = analysis["pair_analyses"]
    cluster_summary = analysis["cluster_summary"]
    if not pair_analyses:
        raise DaySyncError("ANCHOR_SUBTITLE_INVALID", "No cluster pairs available to create candidate")

    relevant_pairs = [pair for pair in pair_analyses if pair["is_inlier"]]
    if not relevant_pairs:
        relevant_pairs = pair_analyses

    video_media_ids = {pair["video_source_media_file_id"] for pair in relevant_pairs}
    audio_media_ids = {pair["audio_source_media_file_id"] for pair in relevant_pairs}
    if len(video_media_ids) != 1 or len(audio_media_ids) != 1:
        raise DaySyncError(
            "ANCHOR_SUBTITLE_INVALID",
            "Cluster candidate spans multiple media files and cannot be saved as one sync result",
        )

    video_media_id = next(iter(video_media_ids))
    audio_media_id = next(iter(audio_media_ids))
    representative_pair = min(
        relevant_pairs,
        key=lambda pair: (
            pair["cluster_deviation_ms"],
            0 if pair["reverse_match_consistent"] else 1,
            -pair["final_score"],
        ),
    )
    proposed_offset_ms = (
        cluster_summary["final_offset_ms"]
        if cluster_summary["final_offset_ms"] is not None
        else cluster_summary["median_offset_ms"]
    )
    video_media = _load_media(connection, video_media_id)

    reverse_match_consistency = (
        cluster_summary["reverse_consistent_count"] / cluster_summary["candidate_count"]
        if cluster_summary["candidate_count"]
        else 0.0
    )
    text_similarity = _average_metric(relevant_pairs, "text_similarity")
    context_similarity = _average_metric(relevant_pairs, "context_similarity")
    candidate_margin = _average_metric(relevant_pairs, "candidate_margin")
    offset_cluster_stability = cluster_summary["inlier_ratio"]
    negative_evidence_count = sum(pair["negative_evidence_count"] for pair in relevant_pairs)
    final_score = max(
        0.0,
        min(
            1.0,
            text_similarity * 0.3
            + context_similarity * 0.2
            + offset_cluster_stability * 0.2
            + reverse_match_consistency * 0.2
            + candidate_margin * 0.1
            - min(negative_evidence_count, 5) * 0.03,
        ),
    )
    confidence_breakdown = {
        "text_similarity": round(text_similarity, 4),
        "context_similarity": round(context_similarity, 4),
        "offset_cluster_stability": round(offset_cluster_stability, 4),
        "reverse_match_consistency": round(reverse_match_consistency, 4),
        "candidate_margin": round(candidate_margin, 4),
        "negative_evidence_count": negative_evidence_count,
        "final_score": round(final_score, 4),
        "cluster_summary": cluster_summary,
        "pair_analyses": pair_analyses,
        "note": note,
    }
    auto_accept_decision = _evaluate_auto_accept(
        cluster_summary=cluster_summary,
        relevant_pairs=relevant_pairs,
        average_candidate_margin=candidate_margin,
    )
    confidence_breakdown["auto_accept_decision"] = auto_accept_decision

    sync_result = {
        "id": new_uuid(),
        "project_id": project_id,
        "session_id": None,
        "video_media_file_id": video_media_id,
        "audio_media_file_id": audio_media_id,
        "video_in_ms": 0,
        "video_out_ms": video_media["duration_ms"],
        "audio_in_ms": proposed_offset_ms,
        "audio_out_ms": proposed_offset_ms + video_media["duration_ms"],
        "offset_ms": proposed_offset_ms,
        "drift_ppm": None,
        "confidence_score": round(final_score, 4),
        "status": "accepted_auto" if auto_accept_decision["eligible"] else "needs_review",
        "source": "auto_text",
        "video_anchor_subtitle_id": representative_pair["video_subtitle_id"],
        "audio_anchor_subtitle_id": representative_pair["audio_subtitle_id"],
        "confidence_breakdown_json": json.dumps(confidence_breakdown, ensure_ascii=False),
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
    }
    connection.execute(
        """
        INSERT INTO sync_results (
          id, project_id, session_id, video_media_file_id, audio_media_file_id, video_in_ms, video_out_ms,
          audio_in_ms, audio_out_ms, offset_ms, drift_ppm, confidence_score, status, source,
          video_anchor_subtitle_id, audio_anchor_subtitle_id, confidence_breakdown_json, created_at, updated_at
        )
        VALUES (:id, :project_id, :session_id, :video_media_file_id, :audio_media_file_id, :video_in_ms,
                :video_out_ms, :audio_in_ms, :audio_out_ms, :offset_ms, :drift_ppm, :confidence_score,
                :status, :source, :video_anchor_subtitle_id, :audio_anchor_subtitle_id,
                :confidence_breakdown_json, :created_at, :updated_at)
        """,
        sync_result,
    )
    connection.commit()
    return {
        "sync_result": sync_result,
        "cluster_summary": cluster_summary,
        "auto_accept_decision": auto_accept_decision,
    }


def review_sync_result(
    connection: sqlite3.Connection,
    project_id: str,
    sync_result_id: str,
    action: str,
    new_offset_ms: int | None = None,
    note: str | None = None,
) -> dict[str, object]:
    sync_result = _load_sync_result(connection, project_id, sync_result_id)
    old_offset_ms = sync_result["offset_ms"]
    updated_at = utc_now_iso()
    status = sync_result["status"]
    offset_ms = old_offset_ms
    audio_in_ms = sync_result["audio_in_ms"]
    audio_out_ms = sync_result["audio_out_ms"]
    review_event_type = action

    if action == "accepted":
        status = "accepted_auto"
    elif action == "rejected":
        status = "rejected"
    elif action == "adjusted":
        if new_offset_ms is None:
            raise DaySyncError("ANCHOR_SUBTITLE_INVALID", "new_offset_ms is required for adjusted review")
        status = "accepted_manual"
        offset_ms = new_offset_ms
        audio_in_ms = new_offset_ms
        audio_out_ms = new_offset_ms + sync_result["video_out_ms"]
    elif action == "commented":
        status = sync_result["status"]
    else:
        raise DaySyncError("ANCHOR_SUBTITLE_INVALID", f"Unsupported review action: {action}")

    connection.execute(
        """
        UPDATE sync_results
        SET status = ?, offset_ms = ?, audio_in_ms = ?, audio_out_ms = ?, updated_at = ?
        WHERE id = ? AND project_id = ?
        """,
        (status, offset_ms, audio_in_ms, audio_out_ms, updated_at, sync_result_id, project_id),
    )
    review_event = {
        "id": new_uuid(),
        "project_id": project_id,
        "sync_result_id": sync_result_id,
        "event_type": review_event_type,
        "old_offset_ms": old_offset_ms,
        "new_offset_ms": offset_ms if action in {"accepted", "adjusted"} else None,
        "note": note,
        "created_at": updated_at,
    }
    connection.execute(
        """
        INSERT INTO review_events (
          id, project_id, sync_result_id, event_type, old_offset_ms, new_offset_ms, note, created_at
        )
        VALUES (:id, :project_id, :sync_result_id, :event_type, :old_offset_ms, :new_offset_ms, :note, :created_at)
        """,
        review_event,
    )
    connection.commit()

    updated_result = connection.execute(
        """
        SELECT sr.id, sr.project_id, sr.video_media_file_id, sr.audio_media_file_id, sr.video_in_ms,
               sr.video_out_ms, sr.audio_in_ms, sr.audio_out_ms, sr.offset_ms, sr.confidence_score,
               sr.status, sr.source, sr.video_anchor_subtitle_id, sr.audio_anchor_subtitle_id,
               sr.confidence_breakdown_json, sr.created_at, sr.updated_at,
               vm.filename AS video_file, am.filename AS audio_file,
               vs.raw_text AS video_anchor_text, aus.raw_text AS audio_anchor_text
        FROM sync_results sr
        JOIN media_files vm ON vm.id = sr.video_media_file_id
        JOIN media_files am ON am.id = sr.audio_media_file_id
        LEFT JOIN subtitles vs ON vs.id = sr.video_anchor_subtitle_id
        LEFT JOIN subtitles aus ON aus.id = sr.audio_anchor_subtitle_id
        WHERE sr.id = ? AND sr.project_id = ?
        """,
        (sync_result_id, project_id),
    ).fetchone()
    review_events = connection.execute(
        """
        SELECT id, sync_result_id, event_type, old_offset_ms, new_offset_ms, note, created_at
        FROM review_events
        WHERE sync_result_id = ?
        ORDER BY created_at DESC
        """,
        (sync_result_id,),
    ).fetchall()
    result_payload = dict(updated_result)
    result_payload["confidence_breakdown"] = _parse_json(result_payload.pop("confidence_breakdown_json"))
    result_payload["review_events"] = [dict(event) for event in review_events]
    return {
        "sync_result": result_payload,
        "review_event": review_event,
    }


def analyze_offset_cluster(
    connection: sqlite3.Connection,
    project_id: str,
    pairs: list[dict[str, str]],
    tolerance_ms: int = 500,
    min_inlier_ratio: float = 0.6,
    min_anchor_count: int = 3,
    context_radius: int = 1,
) -> dict[str, object]:
    if not pairs:
        raise DaySyncError("ANCHOR_SUBTITLE_INVALID", "At least one subtitle pair is required")

    unique_pairs: list[dict[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for pair in pairs:
        pair_key = (pair["video_subtitle_id"], pair["audio_subtitle_id"])
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)
        unique_pairs.append(pair)

    pair_analyses: list[dict[str, object]] = []
    for pair in unique_pairs:
        recommendation = _recommend_auto_candidates_internal(
            connection,
            project_id,
            pair["video_subtitle_id"],
            context_radius=context_radius,
        )
        video_anchor = recommendation["anchor"]
        candidate = next(
            (
                item
                for item in recommendation["candidates"]
                if item["subtitle_id"] == pair["audio_subtitle_id"]
            ),
            None,
        )
        if candidate is None:
            raise DaySyncError(
                "ANCHOR_SUBTITLE_INVALID",
                "Selected audio subtitle is not available for cluster analysis",
                pair,
            )
        if video_anchor["source_start_ms"] is None or candidate["source_start_ms"] is None:
            raise DaySyncError(
                "ANCHOR_SUBTITLE_INVALID",
                "Selected subtitle pair does not have mapped source times",
                pair,
            )

        offset_ms = candidate["source_start_ms"] - video_anchor["source_start_ms"]
        pair_negative_evidence_count = candidate["negative_evidence_count"]
        if video_anchor["mapping_status"] != "ok":
            pair_negative_evidence_count += 1
        if video_anchor["duplicate_count"] > 1:
            pair_negative_evidence_count += 1

        pair_analyses.append(
            {
                "video_subtitle_id": video_anchor["subtitle_id"],
                "video_text": video_anchor["raw_text"],
                "video_source_media_file_id": video_anchor["source_media_file_id"],
                "video_source_filename": video_anchor["source_filename"],
                "video_source_start_ms": video_anchor["source_start_ms"],
                "audio_subtitle_id": candidate["subtitle_id"],
                "audio_text": candidate["raw_text"],
                "audio_source_media_file_id": candidate["source_media_file_id"],
                "audio_source_filename": candidate["source_filename"],
                "audio_source_start_ms": candidate["source_start_ms"],
                "offset_ms": offset_ms,
                "text_similarity": candidate["text_similarity"],
                "context_similarity": candidate["context_similarity"],
                "final_score": candidate["final_score"],
                "candidate_margin": candidate["candidate_margin"],
                "reverse_margin": candidate["reverse_margin"],
                "reverse_match_consistent": candidate["reverse_match_consistent"],
                "negative_evidence_count": pair_negative_evidence_count,
                "mapping_warning": candidate["mapping_warning"] or video_anchor["mapping_warning"],
                "reverse_top_subtitle_id": candidate["reverse_top_subtitle_id"],
                "reverse_top_raw_text": candidate["reverse_top_raw_text"],
            }
        )

    offset_values = [analysis["offset_ms"] for analysis in pair_analyses]
    median_offset_ms = int(round(median(offset_values)))
    inlier_offsets: list[int] = []
    for analysis in pair_analyses:
        cluster_deviation_ms = abs(analysis["offset_ms"] - median_offset_ms)
        is_inlier = cluster_deviation_ms <= tolerance_ms
        analysis["cluster_deviation_ms"] = cluster_deviation_ms
        analysis["is_inlier"] = is_inlier
        if is_inlier:
            inlier_offsets.append(analysis["offset_ms"])

    inlier_count = len(inlier_offsets)
    candidate_count = len(pair_analyses)
    inlier_ratio = inlier_count / candidate_count if candidate_count else 0.0
    passes = candidate_count >= min_anchor_count and inlier_ratio >= min_inlier_ratio and inlier_count > 0
    final_offset_ms = int(round(median(inlier_offsets))) if passes else None

    reasons: list[str] = []
    if candidate_count < min_anchor_count:
        reasons.append("not_enough_anchor_pairs")
    if inlier_ratio < min_inlier_ratio:
        reasons.append("inlier_ratio_below_threshold")
    if any(not analysis["reverse_match_consistent"] for analysis in pair_analyses):
        reasons.append("reverse_match_inconsistency_present")
    if any(analysis["negative_evidence_count"] > 0 for analysis in pair_analyses):
        reasons.append("negative_evidence_present")

    relevant_pairs = [pair for pair in pair_analyses if pair["is_inlier"]]
    if not relevant_pairs:
        relevant_pairs = pair_analyses
    auto_accept_decision = _evaluate_auto_accept(
        cluster_summary={
            "passes": passes,
            "inlier_count": inlier_count,
            "min_anchor_count": min_anchor_count,
        },
        relevant_pairs=relevant_pairs,
        average_candidate_margin=_average_metric(relevant_pairs, "candidate_margin"),
    )

    return {
        "pair_analyses": pair_analyses,
        "cluster_summary": {
            "candidate_count": candidate_count,
            "median_offset_ms": median_offset_ms,
            "final_offset_ms": final_offset_ms,
            "inlier_count": inlier_count,
            "inlier_ratio": round(inlier_ratio, 4),
            "passes": passes,
            "tolerance_ms": tolerance_ms,
            "min_inlier_ratio": min_inlier_ratio,
            "min_anchor_count": min_anchor_count,
            "reverse_consistent_count": sum(
                1 for analysis in pair_analyses if analysis["reverse_match_consistent"]
            ),
            "negative_evidence_pair_count": sum(
                1 for analysis in pair_analyses if analysis["negative_evidence_count"] > 0
            ),
            "reasons": reasons,
        },
        "auto_accept_decision": auto_accept_decision,
    }


def _recommend_auto_candidates_internal(
    connection: sqlite3.Connection,
    project_id: str,
    anchor_subtitle_id: str,
    *,
    context_radius: int,
) -> dict[str, object]:
    anchor = _load_project_subtitle(connection, project_id, anchor_subtitle_id)
    target_track_type = "external_audio" if anchor["track_type"] == "video_ref" else "video_ref"
    anchor_track_rows = _load_track_subtitles(connection, anchor["track_id"])
    target_rows = _load_project_subtitles_by_track_type(connection, project_id, target_track_type)
    target_duplicates = _count_normalized_duplicates(target_rows)
    grouped_target_rows = _group_rows_by_track(target_rows)
    anchor_duplicates = _count_normalized_duplicates(anchor_track_rows)

    anchor_context = _build_context_payload(anchor_track_rows, anchor["id"], context_radius)
    ordered_candidates = _score_target_candidates(
        anchor=anchor,
        anchor_context=anchor_context,
        target_rows=target_rows,
        grouped_target_rows=grouped_target_rows,
        target_duplicates=target_duplicates,
        context_radius=context_radius,
    )
    _apply_candidate_margins(ordered_candidates)

    grouped_anchor_rows = {anchor["track_id"]: anchor_track_rows}
    for candidate in ordered_candidates:
        candidate_row = next(row for row in target_rows if row["id"] == candidate["subtitle_id"])
        candidate_track_rows = grouped_target_rows[candidate_row["track_id"]]
        candidate_context = _build_context_payload(candidate_track_rows, candidate_row["id"], context_radius)
        reverse_candidates = _score_target_candidates(
            anchor=candidate_row,
            anchor_context=candidate_context,
            target_rows=anchor_track_rows,
            grouped_target_rows=grouped_anchor_rows,
            target_duplicates=anchor_duplicates,
            context_radius=context_radius,
        )
        _apply_candidate_margins(reverse_candidates)
        reverse_top_candidate = reverse_candidates[0] if reverse_candidates else None
        candidate["reverse_match_consistent"] = (
            reverse_top_candidate is not None and reverse_top_candidate["subtitle_id"] == anchor["id"]
        )
        candidate["reverse_top_subtitle_id"] = (
            reverse_top_candidate["subtitle_id"] if reverse_top_candidate else None
        )
        candidate["reverse_top_raw_text"] = (
            reverse_top_candidate["raw_text"] if reverse_top_candidate else None
        )
        candidate["reverse_margin"] = (
            reverse_top_candidate["candidate_margin"] if reverse_top_candidate else 0.0
        )

    return {
        "anchor": {
            "subtitle_id": anchor["id"],
            "track_type": anchor["track_type"],
            "track_id": anchor["track_id"],
            "raw_text": anchor["raw_text"],
            "normalized_text": anchor["normalized_text"],
            "source_media_file_id": anchor["source_media_file_id"],
            "source_filename": anchor["source_filename"],
            "source_start_ms": anchor["source_start_ms"],
            "source_end_ms": anchor["source_end_ms"],
            "flat_start_ms": anchor["flat_start_ms"],
            "flat_end_ms": anchor["flat_end_ms"],
            "mapping_status": anchor["mapping_status"],
            "mapping_warning": anchor["mapping_warning"],
            "context_before_text": anchor_context["context_before_text"],
            "context_after_text": anchor_context["context_after_text"],
            "context_window_text": anchor_context["context_window_text"],
            "duplicate_count": anchor_duplicates.get(anchor["normalized_text"], 0),
        },
        "target_track_type": target_track_type,
        "context_radius": context_radius,
        "candidates": ordered_candidates,
    }


def _load_anchor(
    connection: sqlite3.Connection, project_id: str, subtitle_id: str, expected_track_type: str
) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT s.id, s.source_media_file_id, s.source_start_ms, s.source_end_ms, st.track_type
        FROM subtitles s
        JOIN subtitle_tracks st ON st.id = s.track_id
        WHERE s.id = ? AND st.project_id = ?
        """,
        (subtitle_id, project_id),
    ).fetchone()
    if row is None or row["track_type"] != expected_track_type or row["source_media_file_id"] is None:
        raise DaySyncError("ANCHOR_SUBTITLE_INVALID", "Selected anchor subtitle is invalid")
    return row


def _load_media(connection: sqlite3.Connection, media_file_id: str) -> sqlite3.Row:
    row = connection.execute(
        "SELECT id, duration_ms FROM media_files WHERE id = ?",
        (media_file_id,),
    ).fetchone()
    if row is None:
        raise DaySyncError("MEDIA_FILE_NOT_FOUND", "Media file not found for sync result")
    return row


def _load_project_subtitle(connection: sqlite3.Connection, project_id: str, subtitle_id: str) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT s.id, s.track_id, s.subtitle_index, s.flat_start_ms, s.flat_end_ms,
               s.source_media_file_id, s.source_start_ms, s.source_end_ms,
               s.raw_text, s.normalized_text, s.mapping_status, s.mapping_warning,
               st.track_type, st.flat_timeline_id, mf.filename AS source_filename
        FROM subtitles s
        JOIN subtitle_tracks st ON st.id = s.track_id
        LEFT JOIN media_files mf ON mf.id = s.source_media_file_id
        WHERE st.project_id = ? AND s.id = ?
        """,
        (project_id, subtitle_id),
    ).fetchone()
    if row is None:
        raise DaySyncError("ANCHOR_SUBTITLE_INVALID", "Selected anchor subtitle is invalid")
    return row


def _load_track_subtitles(connection: sqlite3.Connection, track_id: str) -> list[sqlite3.Row]:
    rows = connection.execute(
        """
        SELECT s.id, s.track_id, s.subtitle_index, s.flat_start_ms, s.flat_end_ms,
               s.source_media_file_id, s.source_start_ms, s.source_end_ms,
               s.raw_text, s.normalized_text, s.mapping_status, s.mapping_warning,
               st.track_type, st.flat_timeline_id, mf.filename AS source_filename
        FROM subtitles s
        JOIN subtitle_tracks st ON st.id = s.track_id
        LEFT JOIN media_files mf ON mf.id = s.source_media_file_id
        WHERE s.track_id = ?
        ORDER BY s.subtitle_index
        """,
        (track_id,),
    ).fetchall()
    return list(rows)


def _load_project_subtitles_by_track_type(
    connection: sqlite3.Connection, project_id: str, track_type: str
) -> list[sqlite3.Row]:
    rows = connection.execute(
        """
        SELECT s.id, s.track_id, s.subtitle_index, s.flat_start_ms, s.flat_end_ms,
               s.source_media_file_id, s.source_start_ms, s.source_end_ms,
               s.raw_text, s.normalized_text, s.mapping_status, s.mapping_warning,
               st.track_type, st.flat_timeline_id, mf.filename AS source_filename
        FROM subtitles s
        JOIN subtitle_tracks st ON st.id = s.track_id
        LEFT JOIN media_files mf ON mf.id = s.source_media_file_id
        WHERE st.project_id = ? AND st.track_type = ?
        ORDER BY st.id, s.subtitle_index
        """,
        (project_id, track_type),
    ).fetchall()
    return list(rows)


def _group_rows_by_track(rows: list[sqlite3.Row]) -> dict[str, list[sqlite3.Row]]:
    grouped: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        grouped.setdefault(row["track_id"], []).append(row)
    return grouped


def _load_flat_timeline_items(connection: sqlite3.Connection, flat_timeline_id: str) -> list[sqlite3.Row]:
    rows = connection.execute(
        """
        SELECT fti.id, fti.media_file_id, fti.item_index, fti.flat_start_ms, fti.flat_end_ms,
               fti.source_start_ms, fti.source_end_ms, fti.gap_after_ms, mf.filename
        FROM flat_timeline_items fti
        JOIN media_files mf ON mf.id = fti.media_file_id
        WHERE fti.flat_timeline_id = ?
        ORDER BY fti.item_index
        """,
        (flat_timeline_id,),
    ).fetchall()
    return list(rows)


def _empty_auto_conform_preview(
    *,
    reason: str,
    selected_seed_count: int,
    eligible_seed_count: int,
) -> dict[str, object]:
    return {
        "representative_pair": None,
        "anchor_pairs": [],
        "excluded_seeds": [],
        "cluster_summary": {
            "candidate_count": 0,
            "median_offset_ms": None,
            "final_offset_ms": None,
            "inlier_count": 0,
            "inlier_ratio": 0.0,
            "passes": False,
            "tolerance_ms": 500,
            "min_inlier_ratio": 0.6,
            "min_anchor_count": 3,
            "reverse_consistent_count": 0,
            "negative_evidence_pair_count": 0,
            "reasons": [reason],
        },
        "auto_accept_decision": {
            "eligible": False,
            "reasons": [reason],
            "average_candidate_margin": 0.0,
            "min_candidate_margin": AUTO_PASS_MIN_CANDIDATE_MARGIN,
        },
        "preview_segments": [],
        "ready_to_apply": False,
        "selected_seed_count": selected_seed_count,
        "eligible_seed_count": eligible_seed_count,
    }


def _select_auto_conform_seeds(rows: list[sqlite3.Row]) -> tuple[list[sqlite3.Row], list[dict[str, object]]]:
    duplicate_counts = _count_normalized_duplicates(rows)
    grouped_candidates: dict[str, list[sqlite3.Row]] = {}
    excluded_seeds: list[dict[str, object]] = []

    for row in rows:
        rejection_reason = _auto_conform_seed_rejection_reason(row, duplicate_counts)
        if rejection_reason is not None:
            excluded_seeds.append(
                {
                    "subtitle_id": str(row["id"]),
                    "raw_text": str(row["raw_text"]),
                    "source_filename": row["source_filename"],
                    "reason": rejection_reason,
                }
            )
            continue
        media_key = str(row["source_media_file_id"])
        grouped_candidates.setdefault(media_key, []).append(row)

    selected: list[sqlite3.Row] = []
    for media_key, candidates in grouped_candidates.items():
        ordered = sorted(
            candidates,
            key=lambda item: (
                -len(str(item["normalized_text"] or "")),
                int(item["subtitle_index"]),
            ),
        )
        selected.extend(ordered[:AUTO_CONFORM_MAX_SEEDS_PER_MEDIA])
        for row in ordered[AUTO_CONFORM_MAX_SEEDS_PER_MEDIA:]:
            excluded_seeds.append(
                {
                    "subtitle_id": str(row["id"]),
                    "raw_text": str(row["raw_text"]),
                    "source_filename": row["source_filename"],
                    "reason": "exceeds_per_media_seed_limit",
                }
            )

    selected.sort(
        key=lambda item: (
            -len(str(item["normalized_text"] or "")),
            str(item["source_media_file_id"] or ""),
            int(item["subtitle_index"]),
        )
    )
    return selected, excluded_seeds


def _auto_conform_seed_rejection_reason(
    row: sqlite3.Row,
    duplicate_counts: dict[str, int],
) -> str | None:
    normalized_text = str(row["normalized_text"] or "").strip()
    if row["mapping_status"] != "ok":
        return "mapping_not_ok"
    if row["source_media_file_id"] is None or row["source_start_ms"] is None:
        return "subtitle_not_mapped_to_source"
    if not normalized_text:
        return "normalized_text_empty"
    if len(normalized_text) < AUTO_CONFORM_MIN_TEXT_LENGTH:
        return "text_too_short"
    if duplicate_counts.get(normalized_text, 0) > 1:
        return "duplicate_normalized_text"
    return None


def _auto_conform_candidate_rejection_reason(candidate: dict[str, object]) -> str | None:
    normalized_text = str(candidate.get("normalized_text") or "").strip()
    if candidate.get("mapping_status") != "ok":
        return "candidate_mapping_not_ok"
    if candidate.get("source_media_file_id") is None or candidate.get("source_start_ms") is None:
        return "candidate_not_mapped_to_source"
    if not normalized_text:
        return "candidate_normalized_text_empty"
    if len(normalized_text) < AUTO_CONFORM_MIN_TEXT_LENGTH:
        return "candidate_text_too_short"
    if int(candidate.get("duplicate_count") or 0) > 1:
        return "candidate_duplicate_normalized_text"
    return None


def _analyze_auto_conform_pairs(
    anchor_pairs: list[dict[str, object]],
    *,
    tolerance_ms: int,
    min_inlier_ratio: float,
    min_anchor_count: int,
) -> dict[str, object]:
    if not anchor_pairs:
        return {
            "representative_pair": None,
            "anchor_pairs": [],
            "cluster_summary": {
                "candidate_count": 0,
                "median_offset_ms": None,
                "final_offset_ms": None,
                "inlier_count": 0,
                "inlier_ratio": 0.0,
                "passes": False,
                "tolerance_ms": tolerance_ms,
                "min_inlier_ratio": min_inlier_ratio,
                "min_anchor_count": min_anchor_count,
                "reverse_consistent_count": 0,
                "negative_evidence_pair_count": 0,
                "reasons": ["no_anchor_pairs"],
            },
            "auto_accept_decision": {
                "eligible": False,
                "reasons": ["no_anchor_pairs"],
                "average_candidate_margin": 0.0,
                "min_candidate_margin": AUTO_PASS_MIN_CANDIDATE_MARGIN,
            },
        }

    analyzed_pairs = [dict(pair) for pair in anchor_pairs]
    median_offset_ms = int(round(median([int(pair["offset_ms"]) for pair in analyzed_pairs])))
    inlier_offsets: list[int] = []
    for pair in analyzed_pairs:
        cluster_deviation_ms = abs(int(pair["offset_ms"]) - median_offset_ms)
        is_inlier = cluster_deviation_ms <= tolerance_ms
        pair["cluster_deviation_ms"] = cluster_deviation_ms
        pair["is_inlier"] = is_inlier
        if is_inlier:
            inlier_offsets.append(int(pair["offset_ms"]))

    candidate_count = len(analyzed_pairs)
    inlier_count = len(inlier_offsets)
    inlier_ratio = inlier_count / candidate_count if candidate_count else 0.0
    passes = candidate_count >= min_anchor_count and inlier_ratio >= min_inlier_ratio and inlier_count > 0
    final_offset_ms = int(round(median(inlier_offsets))) if passes else None

    reasons: list[str] = []
    if candidate_count < min_anchor_count:
        reasons.append("not_enough_anchor_pairs")
    if inlier_ratio < min_inlier_ratio:
        reasons.append("inlier_ratio_below_threshold")
    if any(not bool(pair["reverse_match_consistent"]) for pair in analyzed_pairs):
        reasons.append("reverse_match_inconsistency_present")
    if any(int(pair["negative_evidence_count"]) > 0 for pair in analyzed_pairs):
        reasons.append("negative_evidence_present")

    relevant_pairs = [pair for pair in analyzed_pairs if pair["is_inlier"]]
    if not relevant_pairs:
        relevant_pairs = analyzed_pairs
    auto_accept_decision = _evaluate_auto_accept(
        cluster_summary={
            "passes": passes,
            "inlier_count": inlier_count,
            "min_anchor_count": min_anchor_count,
        },
        relevant_pairs=relevant_pairs,
        average_candidate_margin=_average_metric(relevant_pairs, "candidate_margin"),
    )
    representative_pair = min(
        relevant_pairs,
        key=lambda pair: (
            int(pair["cluster_deviation_ms"]),
            0 if bool(pair["reverse_match_consistent"]) else 1,
            -float(pair["final_score"]),
        ),
    )

    return {
        "representative_pair": representative_pair,
        "anchor_pairs": analyzed_pairs,
        "cluster_summary": {
            "candidate_count": candidate_count,
            "median_offset_ms": median_offset_ms,
            "final_offset_ms": final_offset_ms,
            "inlier_count": inlier_count,
            "inlier_ratio": round(inlier_ratio, 4),
            "passes": passes,
            "tolerance_ms": tolerance_ms,
            "min_inlier_ratio": min_inlier_ratio,
            "min_anchor_count": min_anchor_count,
            "reverse_consistent_count": sum(
                1 for pair in analyzed_pairs if bool(pair["reverse_match_consistent"])
            ),
            "negative_evidence_pair_count": sum(
                1 for pair in analyzed_pairs if int(pair["negative_evidence_count"]) > 0
            ),
            "reasons": reasons,
        },
        "auto_accept_decision": auto_accept_decision,
    }


def _build_auto_conform_preview_segments(
    connection: sqlite3.Connection,
    project_id: str,
    *,
    representative_video_subtitle_id: str,
    representative_audio_subtitle_id: str,
    track_offset_ms: int,
    confidence_score: float,
) -> list[dict[str, object]]:
    video_anchor = _load_project_subtitle(connection, project_id, representative_video_subtitle_id)
    audio_anchor = _load_project_subtitle(connection, project_id, representative_audio_subtitle_id)
    video_items = _load_flat_timeline_items(connection, video_anchor["flat_timeline_id"])
    audio_items = _load_flat_timeline_items(connection, audio_anchor["flat_timeline_id"])
    created_at = utc_now_iso()
    return _build_track_sync_results(
        project_id=project_id,
        video_anchor=video_anchor,
        audio_anchor=audio_anchor,
        video_items=video_items,
        audio_items=audio_items,
        track_offset_ms=track_offset_ms,
        created_at=created_at,
        status="accepted_auto",
        source="auto_text",
        confidence_score=confidence_score,
        confidence_breakdown={
            "auto_conform_preview": True,
            "track_sync": True,
            "track_offset_ms": track_offset_ms,
        },
    )


def _count_normalized_duplicates(rows: list[sqlite3.Row]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        normalized_text = row["normalized_text"]
        counts[normalized_text] = counts.get(normalized_text, 0) + 1
    return counts


def _build_context_payload(
    rows: list[sqlite3.Row], subtitle_id: str, context_radius: int
) -> dict[str, str]:
    index = next((item_index for item_index, item in enumerate(rows) if item["id"] == subtitle_id), None)
    if index is None:
        return {
            "context_before_text": "",
            "context_after_text": "",
            "context_window_text": "",
        }

    before_items = rows[max(0, index - context_radius) : index]
    after_items = rows[index + 1 : index + 1 + context_radius]
    context_before_text = " ".join(item["raw_text"] for item in before_items).strip()
    context_after_text = " ".join(item["raw_text"] for item in after_items).strip()
    normalized_before = " ".join(item["normalized_text"] for item in before_items).strip()
    normalized_after = " ".join(item["normalized_text"] for item in after_items).strip()
    current_normalized = rows[index]["normalized_text"]
    context_window_text = " | ".join(
        part for part in [normalized_before, current_normalized, normalized_after] if part
    ).strip()
    return {
        "context_before_text": context_before_text,
        "context_after_text": context_after_text,
        "context_window_text": context_window_text,
    }


def _score_target_candidates(
    *,
    anchor: sqlite3.Row,
    anchor_context: dict[str, str],
    target_rows: list[sqlite3.Row],
    grouped_target_rows: dict[str, list[sqlite3.Row]],
    target_duplicates: dict[str, int],
    context_radius: int,
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for row in target_rows:
        candidate_context = _build_context_payload(grouped_target_rows[row["track_id"]], row["id"], context_radius)
        negative_evidence_count = 0
        if row["mapping_status"] != "ok":
            negative_evidence_count += 1
        if target_duplicates.get(row["normalized_text"], 0) > 1:
            negative_evidence_count += 1

        text_similarity = _similarity(anchor["normalized_text"], row["normalized_text"])
        context_similarity = _similarity(
            anchor_context["context_window_text"],
            candidate_context["context_window_text"],
        )
        exact_match_bonus = 0.05 if anchor["normalized_text"] == row["normalized_text"] else 0.0
        final_score = max(
            0.0,
            min(
                1.0,
                text_similarity * 0.7
                + context_similarity * 0.25
                + exact_match_bonus
                - negative_evidence_count * 0.05,
            ),
        )
        candidates.append(
            {
                "subtitle_id": row["id"],
                "track_type": row["track_type"],
                "track_id": row["track_id"],
                "raw_text": row["raw_text"],
                "normalized_text": row["normalized_text"],
                "source_media_file_id": row["source_media_file_id"],
                "source_filename": row["source_filename"],
                "source_start_ms": row["source_start_ms"],
                "source_end_ms": row["source_end_ms"],
                "flat_start_ms": row["flat_start_ms"],
                "flat_end_ms": row["flat_end_ms"],
                "mapping_status": row["mapping_status"],
                "mapping_warning": row["mapping_warning"],
                "text_similarity": round(text_similarity, 4),
                "context_similarity": round(context_similarity, 4),
                "final_score": round(final_score, 4),
                "negative_evidence_count": negative_evidence_count,
                "duplicate_count": target_duplicates.get(row["normalized_text"], 0),
                "context_before_text": candidate_context["context_before_text"],
                "context_after_text": candidate_context["context_after_text"],
                "context_window_text": candidate_context["context_window_text"],
            }
        )
    return sorted(
        candidates,
        key=lambda item: (-item["final_score"], -item["text_similarity"], item["flat_start_ms"]),
    )


def _apply_candidate_margins(candidates: list[dict[str, object]]) -> None:
    for index, candidate in enumerate(candidates):
        next_score = candidates[index + 1]["final_score"] if index + 1 < len(candidates) else 0.0
        candidate["candidate_margin"] = round(candidate["final_score"] - next_score, 4)


def _similarity(left: str | None, right: str | None) -> float:
    left_text = (left or "").strip()
    right_text = (right or "").strip()
    if not left_text and not right_text:
        return 1.0
    if not left_text or not right_text:
        return 0.0
    return SequenceMatcher(None, left_text, right_text).ratio()


def _load_sync_result(connection: sqlite3.Connection, project_id: str, sync_result_id: str) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT id, project_id, video_media_file_id, audio_media_file_id, video_in_ms, video_out_ms,
               audio_in_ms, audio_out_ms, offset_ms, status, source
        FROM sync_results
        WHERE id = ? AND project_id = ?
        """,
        (sync_result_id, project_id),
    ).fetchone()
    if row is None:
        raise DaySyncError("SYNC_RESULT_NOT_FOUND", "Sync result not found")
    return row


def _average_metric(items: list[dict[str, object]], key: str) -> float:
    if not items:
        return 0.0
    return sum(float(item[key]) for item in items) / len(items)


def _build_track_sync_results(
    *,
    project_id: str,
    video_anchor: sqlite3.Row,
    audio_anchor: sqlite3.Row,
    video_items: list[sqlite3.Row],
    audio_items: list[sqlite3.Row],
    track_offset_ms: int,
    created_at: str,
    status: str = "accepted_manual",
    source: str = "manual_anchor",
    confidence_score: float = 1.0,
    confidence_breakdown: dict[str, object] | None = None,
) -> list[dict[str, object]]:
    sync_results: list[dict[str, object]] = []
    confidence_breakdown_json = json.dumps(
        confidence_breakdown or {"manual_anchor": True, "track_sync": True, "track_offset_ms": track_offset_ms},
        ensure_ascii=False,
    )
    for video_item in video_items:
        for audio_item in audio_items:
            common_start_ms = max(
                int(video_item["flat_start_ms"]),
                int(audio_item["flat_start_ms"]) - track_offset_ms,
            )
            common_end_ms = min(
                int(video_item["flat_end_ms"]),
                int(audio_item["flat_end_ms"]) - track_offset_ms,
            )
            if common_start_ms >= common_end_ms:
                continue

            video_in_ms = int(video_item["source_start_ms"]) + (common_start_ms - int(video_item["flat_start_ms"]))
            video_out_ms = int(video_item["source_start_ms"]) + (common_end_ms - int(video_item["flat_start_ms"]))
            audio_in_ms = int(audio_item["source_start_ms"]) + (
                common_start_ms + track_offset_ms - int(audio_item["flat_start_ms"])
            )
            audio_out_ms = int(audio_item["source_start_ms"]) + (
                common_end_ms + track_offset_ms - int(audio_item["flat_start_ms"])
            )
            if video_in_ms >= video_out_ms or audio_in_ms >= audio_out_ms:
                continue

            sync_results.append(
                {
                    "id": new_uuid(),
                    "project_id": project_id,
                    "session_id": None,
                    "video_media_file_id": video_item["media_file_id"],
                    "audio_media_file_id": audio_item["media_file_id"],
                    "video_in_ms": video_in_ms,
                    "video_out_ms": video_out_ms,
                    "audio_in_ms": audio_in_ms,
                    "audio_out_ms": audio_out_ms,
                    "offset_ms": audio_in_ms - video_in_ms,
                    "drift_ppm": None,
                    "confidence_score": round(confidence_score, 4),
                    "status": status,
                    "source": source,
                    "video_anchor_subtitle_id": video_anchor["id"],
                    "audio_anchor_subtitle_id": audio_anchor["id"],
                    "confidence_breakdown_json": confidence_breakdown_json,
                    "created_at": created_at,
                    "updated_at": created_at,
                    "video_file": video_item["filename"],
                    "audio_file": audio_item["filename"],
                    "timeline_start_ms": common_start_ms,
                    "timeline_end_ms": common_end_ms,
                }
            )
    return sync_results


def _clear_existing_manual_sync_results(
    connection: sqlite3.Connection,
    project_id: str,
    sync_results: list[dict[str, object]],
) -> None:
    video_media_ids = sorted({str(item["video_media_file_id"]) for item in sync_results})
    audio_media_ids = sorted({str(item["audio_media_file_id"]) for item in sync_results})
    if not video_media_ids or not audio_media_ids:
        return
    connection.execute(
        """
        DELETE FROM sync_results
        WHERE project_id = ?
          AND source = 'manual_anchor'
          AND video_media_file_id IN ({video_placeholders})
          AND audio_media_file_id IN ({audio_placeholders})
        """.format(
            video_placeholders=",".join("?" for _ in video_media_ids),
            audio_placeholders=",".join("?" for _ in audio_media_ids),
        ),
        (project_id, *video_media_ids, *audio_media_ids),
    )


def _clear_existing_auto_sync_results(connection: sqlite3.Connection, project_id: str) -> None:
    connection.execute(
        """
        DELETE FROM sync_results
        WHERE project_id = ?
          AND source = 'auto_text'
        """,
        (project_id,),
    )


def _evaluate_auto_accept(
    *,
    cluster_summary: dict[str, object],
    relevant_pairs: list[dict[str, object]],
    average_candidate_margin: float,
) -> dict[str, object]:
    reasons: list[str] = []
    if not bool(cluster_summary["passes"]):
        reasons.append("cluster_not_stable_enough")
    if int(cluster_summary["inlier_count"]) < int(cluster_summary["min_anchor_count"]):
        reasons.append("not_enough_inlier_anchors")
    if any(not pair["reverse_match_consistent"] for pair in relevant_pairs):
        reasons.append("reverse_match_not_consistent")
    if average_candidate_margin < AUTO_PASS_MIN_CANDIDATE_MARGIN:
        reasons.append("candidate_margin_too_small")
    if any(pair["negative_evidence_count"] > 0 for pair in relevant_pairs):
        reasons.append("negative_evidence_present")

    return {
        "eligible": not reasons,
        "reasons": reasons,
        "average_candidate_margin": round(average_candidate_margin, 4),
        "min_candidate_margin": AUTO_PASS_MIN_CANDIDATE_MARGIN,
    }


def _parse_json(value: str | None) -> dict[str, object]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
