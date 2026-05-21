from __future__ import annotations

import csv
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = PROJECT_ROOT / "data" / "processed" / "training_dataset_final_local_only.csv"
BACKUP_PATH = PROJECT_ROOT / "data" / "processed" / "training_dataset_final_local_only.before_repair.csv"
REPORT_PATH = PROJECT_ROOT / "data" / "processed" / "training_dataset_extension_report.txt"

REQUIRED_COLUMNS = [
    "input_text",
    "target_text",
    "task_type",
    "source",
    "quality_label",
    "reason",
]
VALID_TASK_TYPES = {"term_definition", "sentence_translation", "context_rewrite"}
PROMPT_PREFIX = "Convert brainrot English to normal English:"


CONCEPTS: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("skill issue", "the problem is caused by someone's lack of ability", [
        ("that's a skill issue", "That problem happened because of someone's lack of ability."),
        ("bro called it a bug but it's a skill issue", "He called it a bug, but the real problem is lack of ability."),
        ("if you lost again, that's lowkey a skill issue", "If you lost again, that is probably due to your lack of ability."),
        ("the exam cooked him because of a skill issue", "He failed badly because he lacked the necessary skill."),
    ]),
    ("rizz", "charm, charisma, or romantic appeal", [
        ("he has rizz", "He has charm or romantic appeal."),
        ("bro has rizz", "He has charm or romantic charisma."),
        ("his rizz carried the conversation", "His charisma helped the conversation succeed."),
        ("she said his rizz is unmatched", "She said his charm is exceptional."),
    ]),
    ("left no crumbs", "did something perfectly with nothing left to criticize", [
        ("she ate and left no crumbs", "She performed extremely well with no flaws."),
        ("that performance left no crumbs", "That performance was excellent and left nothing to criticize."),
        ("he presented the project and left no crumbs", "He presented the project perfectly."),
        ("her outfit left no crumbs", "Her outfit looked excellent in every detail."),
    ]),
    ("ate", "performed extremely well", [
        ("she ate", "She performed extremely well."),
        ("he ate that presentation", "He performed extremely well in that presentation."),
        ("the team ate with that design", "The team did an excellent job with that design."),
        ("she ate and everyone noticed", "She performed so well that everyone noticed."),
    ]),
    ("cooked in the replies", "severely criticized or mocked in the replies", [
        ("bro got cooked in the replies", "He was heavily criticized or mocked in the replies."),
        ("he got cooked in the replies for that take", "He was heavily criticized in the replies for that opinion."),
        ("the replies cooked him instantly", "The replies immediately criticized him harshly."),
        ("she got cooked in the replies after posting that", "She was heavily mocked in the replies after posting that."),
    ]),
    ("mid", "mediocre, average, or unimpressive", [
        ("that movie was mid", "That movie was mediocre and unimpressive."),
        ("the food was lowkey mid", "The food was somewhat mediocre."),
        ("his argument is mid", "His argument is unimpressive."),
        ("the update feels mid", "The update feels average and disappointing."),
    ]),
    ("cooked", "ruined, defeated, or in serious trouble", [
        ("we are cooked", "We are in serious trouble."),
        ("he is cooked after that mistake", "He is in serious trouble after that mistake."),
        ("the project is cooked", "The project is likely ruined."),
        ("after missing the deadline, they were cooked", "After missing the deadline, they were in serious trouble."),
    ]),
    ("delulu", "delusional or unrealistically optimistic", [
        ("she is delulu about that relationship", "She is being unrealistic about that relationship."),
        ("bro is delulu if he thinks that will work", "He is delusional if he thinks that will work."),
        ("that plan sounds delulu", "That plan sounds unrealistic."),
        ("i was delulu for believing the rumor", "I was unrealistic for believing the rumor."),
    ]),
    ("yapping", "talking too much, often without saying much", [
        ("stop yapping", "Stop talking too much."),
        ("he kept yapping during the meeting", "He kept talking too much during the meeting."),
        ("she is yapping about nothing", "She is talking a lot without saying anything important."),
        ("the comment section is just yapping", "The comment section is full of excessive talk."),
    ]),
    ("glazing", "excessively praising someone", [
        ("stop glazing him", "Stop excessively praising him."),
        ("he is glazing that influencer", "He is excessively praising that influencer."),
        ("the fans were glazing the player all night", "The fans excessively praised the player all night."),
        ("that review is pure glazing", "That review is excessive praise."),
    ]),
    ("based", "confidently expressing an approved or authentic opinion", [
        ("that take is based", "That opinion is bold and widely approved."),
        ("she gave a based answer", "She gave a confident and authentic answer."),
        ("based response honestly", "That was honestly a bold and admirable response."),
        ("his comment was based", "His comment was confidently admirable."),
    ]),
    ("cringe", "awkward, embarrassing, or uncomfortable to watch", [
        ("that video is cringe", "That video is embarrassing to watch."),
        ("his speech was so cringe", "His speech was very awkward and embarrassing."),
        ("the joke felt cringe", "The joke felt uncomfortable and embarrassing."),
        ("posting that was cringe", "Posting that was embarrassing."),
    ]),
    ("ratio", "publicly rejected or outperformed in engagement", [
        ("he got ratioed", "His post was publicly rejected through negative engagement."),
        ("that tweet got ratioed hard", "That post received much more criticism than support."),
        ("the replies ratioed him", "The replies publicly rejected his point."),
        ("she ratioed his bad take", "She publicly outperformed and rejected his poor opinion."),
    ]),
    ("slay", "perform excellently or look impressive", [
        ("you slay", "You are doing excellently."),
        ("she slayed that outfit", "She looked excellent in that outfit."),
        ("he slayed the performance", "He performed extremely well."),
        ("the team slayed the launch", "The team handled the launch excellently."),
    ]),
    ("no cap", "without lying or exaggerating", [
        ("no cap, that was amazing", "Honestly, that was amazing."),
        ("he is talented, no cap", "He is genuinely talented."),
        ("no cap, i respect that", "I genuinely respect that."),
        ("that was the best answer, no cap", "That was honestly the best answer."),
    ]),
    ("cap", "a lie or false claim", [
        ("that's cap", "That is a lie."),
        ("he is capping about his score", "He is lying about his score."),
        ("that story is pure cap", "That story is completely false."),
        ("stop the cap", "Stop lying."),
    ]),
    ("bet", "agreement or confirmation", [
        ("bet, i'll be there", "Okay, I will be there."),
        ("you want to meet at eight? bet", "You want to meet at eight? Agreed."),
        ("bet, that works for me", "Okay, that works for me."),
        ("if you send it, i'll review it. bet", "If you send it, I will review it. Agreed."),
    ]),
    ("bffr", "be serious or realistic", [
        ("bffr, that is not true", "Be serious, that is not true."),
        ("bffr, you cannot submit that", "Be realistic, you cannot submit that."),
        ("bffr with that excuse", "Be serious about that excuse."),
        ("bffr, nobody believes that", "Be serious, nobody believes that."),
    ]),
    ("touch grass", "spend time offline and reconnect with reality", [
        ("you need to touch grass", "You need to spend time offline and reconnect with reality."),
        ("touch grass before posting again", "Spend time offline before posting again."),
        ("he should touch grass after that comment", "He should reconnect with reality after that comment."),
        ("the thread needs to touch grass", "The people in the thread need to spend time offline."),
    ]),
    ("main character energy", "confidence as if one is the center of attention", [
        ("she has main character energy", "She carries herself with confident central presence."),
        ("that entrance had main character energy", "That entrance felt confident and attention-grabbing."),
        ("he walked in with main character energy", "He entered as if he were the center of attention."),
        ("the outfit gives main character energy", "The outfit feels confident and attention-grabbing."),
    ]),
    ("NPC", "someone acting generic, predictable, or without independent thought", [
        ("he is acting like an NPC", "He is acting generic and predictable."),
        ("that response was NPC behavior", "That response felt generic and thoughtless."),
        ("the comments are full of NPC takes", "The comments are full of predictable opinions."),
        ("stop giving NPC answers", "Stop giving generic answers."),
    ]),
    ("bro thinks he is him", "someone has exaggerated confidence or self-importance", [
        ("bro thinks he is him", "He is acting overly confident and self-important."),
        ("after one win, bro thinks he is him", "After one win, he is acting excessively confident."),
        ("he scored once and thinks he is him", "He scored once and now acts overly important."),
        ("that caption screams bro thinks he is him", "That caption suggests exaggerated self-confidence."),
    ]),
    ("let him cook", "allow someone to continue because they may produce something good", [
        ("let him cook", "Allow him to continue and see what he can produce."),
        ("wait, let him cook", "Wait, allow him to continue because this may work."),
        ("the idea sounds strange but let him cook", "The idea sounds strange, but allow him to develop it."),
        ("let her cook with that strategy", "Allow her to continue with that strategy."),
    ]),
    ("fanum tax", "taking part of someone's food", [
        ("he took a fanum tax", "He took part of someone else's food."),
        ("bro hit me with the fanum tax", "He took some of my food."),
        ("that bite was fanum tax", "That bite was him taking part of someone else's food."),
        ("stop charging fanum tax", "Stop taking part of other people's food."),
    ]),
    ("skibidi", "absurd, chaotic, or nonsensical", [
        ("that was so skibidi", "That was very absurd and nonsensical."),
        ("the whole situation is skibidi", "The whole situation is chaotic and absurd."),
        ("this comment section became skibidi", "This comment section became nonsensical."),
        ("his explanation was pure skibidi", "His explanation was completely nonsensical."),
    ]),
    ("sigma", "an independent or self-styled dominant person", [
        ("he thinks he is sigma", "He thinks he is independent and dominant."),
        ("that sigma mindset post is cringe", "That post about being independent and dominant is embarrassing."),
        ("bro called himself sigma", "He described himself as independently dominant."),
        ("the edit makes him look sigma", "The edit portrays him as independent and dominant."),
    ]),
    ("gyatt", "an exaggerated reaction to someone's body or appearance", [
        ("the comments just say gyatt", "The comments are exaggerated reactions to someone's appearance."),
        ("he yelled gyatt in the chat", "He made an exaggerated comment about someone's appearance in the chat."),
        ("that gyatt comment was unnecessary", "That exaggerated appearance comment was unnecessary."),
        ("the stream chat turned into gyatt spam", "The stream chat became spam about someone's appearance."),
    ]),
    ("lowkey", "somewhat or secretly", [
        ("lowkey, i agree", "I somewhat agree."),
        ("that was lowkey funny", "That was somewhat funny."),
        ("i am lowkey nervous", "I am somewhat nervous."),
        ("lowkey this works", "This actually works somewhat well."),
    ]),
    ("highkey", "very openly or strongly", [
        ("highkey, that was amazing", "That was openly very impressive."),
        ("i highkey disagree", "I strongly disagree."),
        ("that answer is highkey wrong", "That answer is clearly wrong."),
        ("she highkey carried the team", "She very clearly carried the team."),
    ]),
    ("drip", "stylish clothing or appearance", [
        ("his drip is clean", "His outfit is stylish."),
        ("she has serious drip", "She has very stylish fashion."),
        ("that jacket has drip", "That jacket looks stylish."),
        ("the whole fit has drip", "The entire outfit is stylish."),
    ]),
    ("lore", "background story or context", [
        ("what is the lore here", "What is the background context here?"),
        ("his lore is wild", "His background story is surprising."),
        ("i need the full lore", "I need the full background context."),
        ("the group chat lore is complicated", "The background context of the group chat is complicated."),
    ]),
    ("canon event", "an unavoidable formative event", [
        ("that breakup was a canon event", "That breakup was an unavoidable formative experience."),
        ("failing once is a canon event", "Failing once is a formative event that many people experience."),
        ("this is his canon event", "This is an important formative moment for him."),
        ("everyone has a canon event like that", "Everyone has a formative experience like that."),
    ]),
    ("side quest", "an unrelated or optional activity", [
        ("this errand became a side quest", "This errand became an unrelated extra activity."),
        ("he went on a side quest during lunch", "He did an unrelated activity during lunch."),
        ("that task is a side quest", "That task is optional and unrelated."),
        ("we accidentally started a side quest", "We accidentally began an unrelated extra activity."),
    ]),
    ("brainrot", "internet-overuse language or absurd meme content", [
        ("this app is pure brainrot", "This app is full of absurd internet meme content."),
        ("my feed is brainrot today", "My feed is full of low-quality internet meme content today."),
        ("that joke is brainrot", "That joke is absurd internet humor."),
        ("i consumed too much brainrot", "I consumed too much absurd online content."),
    ]),
    ("chronically online", "spending so much time online that perspective becomes distorted", [
        ("that take is chronically online", "That opinion shows a distorted internet-centered perspective."),
        ("he sounds chronically online", "He sounds like he spends too much time online."),
        ("this argument is chronically online", "This argument reflects an overly internet-centered viewpoint."),
        ("log off, you are chronically online", "You should go offline because your perspective is too internet-centered."),
    ]),
    ("goated", "excellent or among the best", [
        ("that player is goated", "That player is excellent and among the best."),
        ("this song is goated", "This song is excellent."),
        ("her answer was goated", "Her answer was excellent."),
        ("the old version was goated", "The old version was among the best."),
    ]),
    ("fell off", "declined in quality, popularity, or performance", [
        ("that creator fell off", "That creator declined in quality or popularity."),
        ("the show fell off after season two", "The show declined in quality after season two."),
        ("he fell off this year", "His performance declined this year."),
        ("the brand fell off badly", "The brand declined badly."),
    ]),
    ("caught in 4K", "clearly caught doing something wrong", [
        ("he got caught in 4K", "He was clearly caught doing something wrong."),
        ("the screenshot caught her in 4K", "The screenshot clearly exposed her mistake."),
        ("bro was caught in 4K lying", "He was clearly caught lying."),
        ("that video caught them in 4K", "That video clearly showed them doing something wrong."),
    ]),
    ("living rent free", "remaining in someone's thoughts without effort", [
        ("that comment is living rent free in my head", "That comment is staying in my mind."),
        ("he is living rent free in their heads", "They keep thinking about him without him doing anything."),
        ("the joke lives rent free in my head", "The joke keeps staying in my mind."),
        ("that moment is living rent free", "That moment keeps staying in people's thoughts."),
    ]),
    ("vibe check", "judgment of someone's mood, behavior, or social fit", [
        ("he failed the vibe check", "His behavior did not match the expected mood or social standard."),
        ("that answer passed the vibe check", "That answer fit the mood well."),
        ("the place did not pass the vibe check", "The place did not feel socially comfortable."),
        ("quick vibe check, are we good", "Quickly checking the mood, is everything okay?"),
    ]),
    ("understood the assignment", "performed exactly as expected or better", [
        ("she understood the assignment", "She performed exactly as expected and did very well."),
        ("the designer understood the assignment", "The designer delivered exactly what was needed."),
        ("this outfit understood the assignment", "This outfit fits the goal extremely well."),
        ("he understood the assignment with that answer", "He answered exactly as needed."),
    ]),
    ("it's giving", "it strongly suggests or has the vibe of something", [
        ("it's giving main character", "It strongly gives the impression of being central and confident."),
        ("the outfit is giving expensive", "The outfit strongly looks expensive."),
        ("this room is giving cozy", "This room strongly feels cozy."),
        ("his apology is giving fake", "His apology strongly seems fake."),
    ]),
    ("serving", "presenting a strong look, attitude, or performance", [
        ("she is serving looks", "She is presenting a very impressive appearance."),
        ("he is serving confidence", "He is presenting strong confidence."),
        ("that outfit is serving", "That outfit looks very impressive."),
        ("the team is serving professionalism", "The team is presenting strong professionalism."),
    ]),
    ("sus", "suspicious or questionable", [
        ("that excuse is sus", "That excuse is suspicious."),
        ("he acted sus after the meeting", "He acted suspicious after the meeting."),
        ("the link looks sus", "The link looks suspicious."),
        ("that timing is sus", "That timing is questionable."),
    ]),
    ("vibing", "relaxing, enjoying, or matching the mood", [
        ("we are just vibing", "We are just relaxing and enjoying ourselves."),
        ("she was vibing with the music", "She was enjoying the music."),
        ("the team is vibing today", "The team has a good mood today."),
        ("i am vibing with this design", "I like this design and its mood."),
    ]),
    ("big yikes", "a strong negative reaction to something embarrassing or bad", [
        ("that mistake was big yikes", "That mistake was very embarrassing."),
        ("his comment is big yikes", "His comment is seriously bad or embarrassing."),
        ("big yikes, that answer was wrong", "That answer was very wrong and embarrassing."),
        ("the update is big yikes", "The update is seriously disappointing."),
    ]),
    ("W take", "a good or winning opinion", [
        ("that is a W take", "That is a good opinion."),
        ("her review was a W take", "Her review was a strong and correct opinion."),
        ("W take honestly", "That is honestly a good opinion."),
        ("he had a W take about the issue", "He had a good opinion about the issue."),
    ]),
    ("L take", "a bad or losing opinion", [
        ("that is an L take", "That is a bad opinion."),
        ("his comment was an L take", "His comment was a poor opinion."),
        ("L take honestly", "That is honestly a bad opinion."),
        ("she posted an L take", "She posted a poor opinion."),
    ]),
    ("W", "a win or positive outcome", [
        ("that's a W", "That is a win."),
        ("passing the test is a W", "Passing the test is a positive outcome."),
        ("this update is a W", "This update is a good outcome."),
        ("huge W for the team", "This is a major win for the team."),
    ]),
    ("L", "a loss or negative outcome", [
        ("that's an L", "That is a loss."),
        ("missing the deadline is an L", "Missing the deadline is a negative outcome."),
        ("this decision is an L", "This decision is a bad outcome."),
        ("huge L for the project", "This is a major loss for the project."),
    ]),
    ("opps", "opponents or enemies", [
        ("the opps are watching", "The opponents are watching."),
        ("he posted just to annoy the opps", "He posted just to annoy his opponents."),
        ("the opps are mad", "The opponents are upset."),
        ("don't let the opps see this", "Do not let the opponents see this."),
    ]),
    ("pressed", "upset, bothered, or defensive", [
        ("he is pressed about the comment", "He is upset about the comment."),
        ("why are you so pressed", "Why are you so upset?"),
        ("she got pressed over nothing", "She became upset over something minor."),
        ("the replies are pressed", "The people replying are upset."),
    ]),
    ("valid", "reasonable, acceptable, or understandable", [
        ("that concern is valid", "That concern is reasonable."),
        ("your reaction is valid", "Your reaction is understandable."),
        ("valid point honestly", "That is honestly a reasonable point."),
        ("feeling tired is valid", "Feeling tired is understandable."),
    ]),
    ("real", "relatable, true, or strongly agreed with", [
        ("real", "That is relatable or true."),
        ("that comment is real", "That comment is relatable and true."),
        ("real, i felt that", "That is relatable; I understand that feeling."),
        ("he said something real", "He said something true and relatable."),
    ]),
    ("say less", "understood; no more explanation is needed", [
        ("say less, i'll handle it", "Understood, I will handle it."),
        ("say less, we can go", "Understood, we can go."),
        ("you need help? say less", "You need help? I understand and will help."),
        ("say less, that plan works", "Understood, that plan works."),
    ]),
    ("periodt", "emphatic agreement or finality", [
        ("she is the best, periodt", "She is the best, with no further debate."),
        ("we deserve better, periodt", "We deserve better, and that is final."),
        ("that answer wins, periodt", "That answer wins, with no further argument."),
        ("protect your peace, periodt", "Protect your peace, and treat that as final."),
    ]),
    ("ick", "a sudden feeling of dislike or loss of attraction", [
        ("that gave me the ick", "That made me suddenly dislike it."),
        ("his behavior gave her the ick", "His behavior made her lose attraction."),
        ("the rude comment was an ick", "The rude comment caused sudden dislike."),
        ("that habit gives me the ick", "That habit makes me feel sudden dislike."),
    ]),
    ("simp", "someone showing excessive devotion or attention", [
        ("he is simping for her", "He is showing excessive devotion to her."),
        ("stop being a simp", "Stop showing excessive devotion."),
        ("the comment section is simping", "The comment section is excessively praising someone."),
        ("he simped over the influencer", "He showed excessive admiration for the influencer."),
    ]),
    ("stan", "to strongly support or admire someone", [
        ("i stan that artist", "I strongly support that artist."),
        ("the fans stan her", "The fans strongly admire her."),
        ("we stan a responsible decision", "We strongly approve of a responsible decision."),
        ("they stan the team no matter what", "They strongly support the team regardless of circumstances."),
    ]),
    ("tea", "gossip, news, or revealing information", [
        ("spill the tea", "Share the gossip or revealing information."),
        ("what's the tea", "What is the gossip or news?"),
        ("she has tea about the meeting", "She has revealing information about the meeting."),
        ("the tea is that he quit", "The news is that he quit."),
    ]),
]


def make_row(input_text: str, target_text: str, task_type: str, reason: str) -> dict[str, str]:
    return {
        "input_text": f"{PROMPT_PREFIX} {input_text.strip()}",
        "target_text": target_text.strip(),
        "task_type": task_type,
        "source": "manual_gold_examples",
        "quality_label": "synthetic_high_quality",
        "reason": reason,
    }


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def is_valid_row(row: dict[str, str]) -> bool:
    return (
        all((row.get(column) or "").strip() for column in REQUIRED_COLUMNS)
        and (row.get("input_text") or "").startswith(PROMPT_PREFIX)
        and (row.get("task_type") or "") in VALID_TASK_TYPES
    )


def build_extension_rows(existing: list[dict[str, str]], target_count: int) -> list[dict[str, str]]:
    seen = {
        (
            (row.get("input_text") or "").strip().casefold(),
            (row.get("target_text") or "").strip().casefold(),
        )
        for row in existing
    }
    additions: list[dict[str, str]] = []

    def add(row: dict[str, str]) -> None:
        key = (row["input_text"].casefold(), row["target_text"].casefold())
        if key in seen or len(existing) + len(additions) >= target_count:
            return
        seen.add(key)
        additions.append(row)

    for term, meaning, examples in CONCEPTS:
        add(make_row(term, f"This means {meaning}.", "term_definition", f"Gold definition for {term}."))
        add(make_row(f"what does {term} mean", f"It means {meaning}.", "term_definition", f"Question form for {term}."))
        for slang_text, normal_text in examples:
            add(make_row(slang_text, normal_text, "sentence_translation", f"Gold sentence example for {term}."))
        for slang_text, normal_text in examples[:4]:
            add(
                make_row(
                    f"honestly, {slang_text}",
                    f"Honestly, {normal_text[0].lower() + normal_text[1:]}",
                    "context_rewrite",
                    f"Context rewrite for {term}.",
                )
            )

    supplement_rows = [
        ("his rizz is unreal", "His charm is extremely impressive.", "sentence_translation", "Extra gold rizz sentence."),
        ("that is not a skill issue, it is a system problem", "That is not caused by lack of ability; it is a system problem.", "sentence_translation", "Extra gold skill issue contrast."),
        ("she left absolutely no crumbs in the final round", "She performed perfectly in the final round.", "sentence_translation", "Extra gold left no crumbs sentence."),
        ("the replies cooked that terrible opinion", "The replies harshly criticized that terrible opinion.", "sentence_translation", "Extra gold cooked in replies sentence."),
        ("honestly, this whole thread needs to touch grass", "Honestly, everyone in this thread needs to spend time offline and reconnect with reality.", "context_rewrite", "Extra gold touch grass rewrite."),
        ("lowkey, that apology is giving fake", "That apology somewhat seems insincere.", "context_rewrite", "Extra gold it's giving rewrite."),
    ]
    for slang_text, normal_text, task_type, reason in supplement_rows:
        add(make_row(slang_text, normal_text, task_type, reason))

    if len(existing) + len(additions) < target_count:
        raise RuntimeError(
            f"Only reached {len(existing) + len(additions)} rows; add more concept examples."
        )
    return additions


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REQUIRED_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    rows = load_rows(DATASET_PATH)
    valid_rows = [row for row in rows if is_valid_row(row)]
    malformed_count = len(rows) - len(valid_rows)

    if not BACKUP_PATH.exists():
        shutil.copy2(DATASET_PATH, BACKUP_PATH)

    base_rows = valid_rows[:3600]
    additions = build_extension_rows(base_rows, 4200)
    final_rows = base_rows + additions
    write_rows(DATASET_PATH, final_rows)

    report = [
        "Training dataset repair and extension report",
        "",
        f"original_rows: {len(rows)}",
        f"valid_rows_before_repair: {len(valid_rows)}",
        f"malformed_rows_removed: {malformed_count + max(0, len(valid_rows) - len(base_rows))}",
        f"base_rows_kept: {len(base_rows)}",
        f"manual_gold_rows_added: {len(additions)}",
        f"final_rows: {len(final_rows)}",
        f"backup_path: {BACKUP_PATH}",
        "",
        "notes:",
        "- Kept the original Gemini synthetic rows 1-3600.",
        "- Removed malformed manually pasted rows after row 3600.",
        "- Added manual_gold_examples focused on phrases the model answered incorrectly.",
    ]
    REPORT_PATH.write_text("\n".join(report) + "\n", encoding="utf-8")

    print("\n".join(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
