#!/usr/bin/env python3
"""Build progressive ASS karaoke subtitles from authoritative lyrics plus LRC or TSV timing."""

from __future__ import annotations

import argparse
import csv
import re
import statistics
from dataclasses import dataclass
from pathlib import Path


TIMESTAMP = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")
VISIBLE = re.compile(r"[\w\u3400-\u9fff]", re.UNICODE)


@dataclass
class TimedChar:
    char: str
    start: float
    end: float


@dataclass
class Event:
    start: float
    end: float
    text: str
    char_ends: list[float] | None = None


def normalized(text: str) -> str:
    return "".join(character.casefold() for character in text if VISIBLE.match(character))


def ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    seconds -= hours * 3600
    minutes = int(seconds // 60)
    seconds -= minutes * 60
    return f"{hours}:{minutes:02d}:{seconds:05.2f}"


def parse_lrc(path: Path, maximum_span: float) -> list[TimedChar]:
    entries: list[tuple[float, str]] = []
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        stamps = TIMESTAMP.findall(raw)
        text = TIMESTAMP.sub("", raw).strip()
        content = normalized(text)
        if not content:
            continue
        for minute, second in stamps:
            entries.append((int(minute) * 60 + float(second), content))
    entries.sort(key=lambda item: item[0])
    if not entries:
        raise ValueError("LRC contains no timestamped lyric text")

    rates: list[float] = []
    for (start, text), (next_start, _) in zip(entries, entries[1:]):
        gap = next_start - start
        if 0.25 <= gap <= maximum_span:
            rates.append(gap / max(1, len(text)))
    seconds_per_char = statistics.median(rates) if rates else 0.30

    result: list[TimedChar] = []
    for index, (start, text) in enumerate(entries):
        natural_end = entries[index + 1][0] if index + 1 < len(entries) else start + seconds_per_char * len(text)
        if natural_end - start > maximum_span:
            natural_end = start + min(maximum_span, max(1.2, seconds_per_char * len(text)))
        duration = max(0.10, natural_end - start)
        for char_index, character in enumerate(text):
            char_start = start + duration * char_index / len(text)
            char_end = start + duration * (char_index + 1) / len(text)
            result.append(TimedChar(character, char_start, char_end))
    return result


def align_target(target: str, source: str) -> tuple[list[int | None], float]:
    """Align the complete target to the best source substring using semi-global DP."""
    n, m = len(target), len(source)
    gap = -2
    previous = [0] * (m + 1)
    trace = [bytearray(m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        current = [gap * i] + [0] * m
        trace[i][0] = 1
        for j in range(1, m + 1):
            diagonal = previous[j - 1] + (3 if target[i - 1] == source[j - 1] else -2)
            up = previous[j] + gap
            left = current[j - 1] + gap
            best = max(diagonal, up, left)
            current[j] = best
            trace[i][j] = 0 if best == diagonal else (1 if best == up else 2)
        previous = current

    j = max(range(m + 1), key=previous.__getitem__)
    i = n
    mapping: list[int | None] = [None] * n
    matches = 0
    while i > 0:
        direction = trace[i][j]
        if direction == 0 and j > 0:
            mapping[i - 1] = j - 1
            matches += target[i - 1] == source[j - 1]
            i -= 1
            j -= 1
        elif direction == 1 or j == 0:
            i -= 1
        else:
            j -= 1
    return mapping, matches / max(1, n)


def interpolate_mapping(mapping: list[int | None]) -> list[int]:
    known = [index for index, value in enumerate(mapping) if value is not None]
    if not known:
        raise ValueError("No lyric characters aligned to the LRC")
    result = [int(value) if value is not None else -1 for value in mapping]
    for index in range(len(result)):
        if result[index] >= 0:
            continue
        left = max((item for item in known if item < index), default=None)
        right = min((item for item in known if item > index), default=None)
        if left is None:
            result[index] = max(0, result[right] - (right - index))  # type: ignore[index]
        elif right is None:
            result[index] = result[left] + (index - left)
        else:
            fraction = (index - left) / (right - left)
            result[index] = round(result[left] + fraction * (result[right] - result[left]))
    return result


def events_from_lrc(lyrics: list[str], chars: list[TimedChar], offset: float) -> tuple[list[Event], float]:
    target = "".join(normalized(line) for line in lyrics)
    source = "".join(item.char for item in chars)
    mapping_raw, ratio = align_target(target, source)
    mapping = interpolate_mapping(mapping_raw)
    events: list[Event] = []
    cursor = 0
    for line in lyrics:
        clean = normalized(line)
        indices = mapping[cursor : cursor + len(clean)]
        cursor += len(clean)
        timed = [chars[min(max(0, index), len(chars) - 1)] for index in indices]
        start = timed[0].start + offset
        end = timed[-1].end + offset
        ends = [item.end + offset for item in timed]
        events.append(Event(start, end, line, ends))
    return events, ratio


def events_from_tsv(path: Path) -> list[Event]:
    events: list[Event] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = csv.reader(handle, delimiter="\t")
        for row_number, row in enumerate(rows, 1):
            if not row or all(not cell.strip() for cell in row):
                continue
            if row[0].strip().lower() == "start":
                continue
            if len(row) < 3:
                raise ValueError(f"TSV row {row_number} must contain start, end, and text")
            start, end = float(row[0]), float(row[1])
            text = "\t".join(row[2:]).strip()
            if end <= start or not normalized(text):
                raise ValueError(f"Invalid TSV event on row {row_number}")
            events.append(Event(start, end, text))
    if not events:
        raise ValueError("TSV contains no timing events")
    return events


def karaoke_text(event: Event) -> str:
    visible_positions = [index for index, character in enumerate(event.text) if VISIBLE.match(character)]
    if not visible_positions:
        return event.text
    if event.char_ends and len(event.char_ends) == len(visible_positions):
        boundaries = event.char_ends
    else:
        span = event.end - event.start
        boundaries = [event.start + span * (index + 1) / len(visible_positions) for index in range(len(visible_positions))]
    output: list[str] = []
    previous = event.start
    boundary_index = 0
    for character in event.text:
        if VISIBLE.match(character):
            duration = max(1, round((boundaries[boundary_index] - previous) * 100))
            output.append(f"{{\\kf{duration}}}{character}")
            previous = boundaries[boundary_index]
            boundary_index += 1
        else:
            output.append(character)
    return "".join(output)


def write_ass(path: Path, events: list[Event], width: int, height: int, font: str, font_size: int | None) -> None:
    size = font_size or max(34, round(height * 0.067))
    margin = max(36, round(height * 0.091))
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes
WrapStyle: 2
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,{font},{size},&H0000D7FF,&H00FFFFFF,&H00101010,&H78000000,-1,0,0,0,100,100,2,0,1,4,1.5,2,70,70,{margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for event in events:
        if event.end <= 0:
            continue
        render_event = Event(
            max(0.0, event.start),
            event.end,
            event.text,
            [max(0.0, value) for value in event.char_ends] if event.char_ends else None,
        )
        lines.append(
            f"Dialogue: 0,{ass_time(render_event.start)},{ass_time(render_event.end)},Karaoke,,0,0,0,,{karaoke_text(render_event)}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--lrc", type=Path)
    source.add_argument("--timings", type=Path, help="TSV with start, end, text")
    parser.add_argument("--lyrics", type=Path, help="Authoritative UTF-8 lyrics, one display line per line")
    clock = parser.add_mutually_exclusive_group()
    clock.add_argument("--offset", type=float, default=None, help="Seconds added to all LRC timestamps")
    clock.add_argument("--first-line-at", type=float, help="Video time for the first supplied lyric line")
    parser.add_argument("--maximum-lrc-span", type=float, default=6.0)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--font", default="PingFang SC")
    parser.add_argument("--font-size", type=int)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.lrc:
        if not args.lyrics:
            parser.error("--lyrics is required with --lrc")
        lyrics = [line.strip() for line in args.lyrics.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
        chars = parse_lrc(args.lrc, args.maximum_lrc_span)
        preliminary, ratio = events_from_lrc(lyrics, chars, 0.0)
        offset = args.offset if args.offset is not None else 0.0
        if args.first_line_at is not None:
            offset = args.first_line_at - preliminary[0].start
        events, _ = events_from_lrc(lyrics, chars, offset)
        print(f"match_ratio={ratio:.4f}")
        print(f"lrc_offset_seconds={offset:.3f}")
    else:
        if args.lyrics:
            parser.error("--lyrics is not used with --timings; TSV text is authoritative")
        if args.offset is not None or args.first_line_at is not None:
            parser.error("clock options apply only with --lrc")
        events = events_from_tsv(args.timings)

    write_ass(args.output, events, args.width, args.height, args.font, args.font_size)
    print(f"events={len(events)}")
    print(f"first_event={events[0].start:.3f}")
    print(f"last_event={events[-1].end:.3f}")
    print(args.output)


if __name__ == "__main__":
    main()
