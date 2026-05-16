# Dataset Report

Generated at: `2026-05-16T13:20:19`
Quality mode: `strict`

## Files Processed

- Supported raw files processed from `data/raw/`: 0
- Compatible seed files processed from `data/processed/`: 2

### File Names Processed

- `data\processed\slang_terms.csv` (supplemental) - loaded 158 rows, extracted 158 pairs
  - note: used glossary columns (term -> meaning)
- `data\processed\huggingface_parallel_dataset.csv` (supplemental) - loaded 14492 rows, extracted 14492 pairs
  - note: used paired columns (text -> standard_text)

### Unsupported Raw Files Skipped

- `data\raw\.gitkeep`
- `data\raw\view-source_https___en.wikipedia.org_wiki_Glossary_of_2020s_slang.html`
- `data\raw\wiki_2020s_slang.html`

### Unreadable Files

- None

### Files With No Usable Pair Columns

- None

## Dataset Counts

- Rows before cleaning: 14650
- Rows after baseline cleaning (`brainrot_dataset.csv`): 8984
- Final cleaned row count (`brainrot_dataset_cleaned.csv`): 8300
- Training-ready row count (`brainrot_dataset_training_ready.csv`): 8252
- Rows flagged as bad: 684
- Duplicates removed: 5661
- Missing value count: 0
- Identical brainrot/normal rows removed: 0
- URL-only rows removed: 0
- Symbol-only rows removed: 0
- Too short rows removed: 0
- Too long rows removed: 5
- Rows removed by broken-fragment filter: 0
- Rows removed by hallucination phrase filter: 626
- Rows removed by definition-substitution filter: 21
- Rows removed by length-ratio filter: 116
- Rows removed by low-overlap filter: 355
- Rows removed by score-only fallback: 0
- Training-ready rows rewritten: 77
- Training-ready rows dropped: 48
- Training-ready glossary rows rewritten: 77
- Training-ready glossary rows dropped: 48
- Training-ready sentence rows dropped: 0

_Quality filter counts can overlap when one row triggers multiple checks._

## Warnings

- No high-priority dataset-size or similarity warnings were triggered.

## Top 20 Most Common Slang Or Brainrot Terms

| term | count |
|---|---|
| acoustic | 1 |
| and i oop | 1 |
| ate | 1 |
| aura | 1 |
| baddie | 1 |
| ball knowledge | 1 |
| bar(s) | 1 |
| based | 1 |
| basic | 1 |
| bde | 1 |
| beige flag | 1 |
| bestie | 1 |
| bet | 1 |
| bffr | 1 |
| big back | 1 |
| big yikes | 1 |
| blud | 1 |
| bop | 1 |
| brainrot | 1 |
| bro | 1 |

## Sample 20 Flagged Bad Pairs

| brainrot | normal | reason_flagged |
|---|---|---|
| She's such a pick me girl, always saying she's not like other girls. | She's such a someone seeking attention by claiming uniqueness, always saying she's not like other girls. | definition_substitution: broken_noun_phrase, definition_phrase: someone seeking attention by claiming uniqueness |
| I waited all day for him to text me back. I'm such a clown. | I waited all day for him to text me back. I'm such a someone who embarrassed themselves. | definition_substitution: broken_noun_phrase, definition_phrase: someone who embarrassed themselves |
| My boss is such a boomer, doesn't even know how to use Zoom. | My boss is such a someone with outdated views, doesn't even know how to use Zoom. | definition_substitution: broken_noun_phrase, definition_phrase: someone with outdated views |
| She's acting like such an NPC, just going with the flow. | She's acting like such an someone without independent thought, just going with the flow. | definition_substitution: broken_noun_phrase, definition_phrase: someone without independent thought |
| I lost my keys again, 55555! | I lost my keys again, crying your eyes out! | definition_substitution: definition_phrase: crying your eyes out |
| That NPC just gave me a quest. | That someone without independent thought just gave me a quest. | definition_substitution: definition_phrase: someone without independent thought |
| He ghosted me months ago, and now he's zombie-ing by texting me again. | He ghosted me months ago, and now he's this happens after someone ghosts you, and then decides to start talking to you again like nothing ever happened. by texting me again. | definition_substitution: definition_phrase: this happens after someone |
| He nailed the jump, YEET! | He nailed the jump, throw forcefully! | definition_substitution: definition_phrase: throw forcefully |
| He's such a Chad, always winning at everything. | He's such a a supremely confident person, always winning at everything. | definition_substitution: double_determiner |
| Her clapback to that troll was savage. | Her a sharp witty response to that troll was savage. | definition_substitution: double_determiner |
| Keanu Reeves is my dad. | Keanu Reeves is my a man I deeply admire. | definition_substitution: double_determiner |
| She's such an e-girl with her neon eyeliner and platform boots. | She's such an a young woman with internet-influenced alternative style with her neon eyeliner and platform boots. | definition_substitution: double_determiner |
| That player is the GOAT of basketball! | That player is the the greatest of all time of basketball! | definition_substitution: double_determiner |
| he wrote her a poem after one date down bad already | He wrote her a poem after the first date. | definition_substitution: double_determiner |
| she got an A on the assignment she did that morning cracked procrastinator | She got an A on the assignment she did the morning it was due. | definition_substitution: double_determiner |
| Beyoncé is such a mom. | Beyoncé is such a a woman I deeply admire. | definition_substitution: double_determiner, definition_phrase: a woman i deeply admire |
| Here's my 0.02 on the situation: We should wait. | Here's my my two cents worth on the situation: We should wait. | definition_substitution: double_determiner, definition_phrase: my two cents worth |
| He's such an e-boy with those black nails and chains. | He's such an a young man with internet-influenced alternative style with those black nails and chains. | definition_substitution: double_determiner, definition_phrase: young man with internet-influenced alternative style |
| She posted it on her finsta, not her main account. | She posted it on her a second instagram account where someone can post things that they're too afraid to post on their main account. not her main account. | definition_substitution: double_determiner; length_ratio: normal words 28 vs brainrot 10 (2.80x) |
| She dragged him for his terrible performance. | She publicly and harshly criticizeged him for his terrible performance. | definition_substitution: malformed_inflection |

## Sample 20 Cleaned Pairs

| brainrot | normal |
|---|---|
| phone case seen better days fr 📱😬 lookin worn out, time for a new drip? ✨ protect the tech | My phone case is getting old. |
| on my fitness journey rn 💪 tryna get healthy fr 🙏 grind includes health king/queen | I'm working on my fitness. |
| her advice u can actually USE fr ✨🛠️ actionable queen gives clear steps 🙏 helpful guidance | She provides clear, actionable advice. |
| face card | An attractive face. Sometimes defined as never declining or receding. |
| hydration check mid-workout! 💧 gotta remember to sip fr, dont wanna cramp up 🙏💪 fuel the engine | I need to remember to stay hydrated during workouts. |
| bro explores abandoned buildings?? 🏚️ adventurous king loves urban exploration fr 🙏 cool pics but be safe tho | He has a passion for urban exploration. |
| bro crashed out after failing and straight up dropped the whole course | After failing the exam he impulsively dropped the entire course. |
| tryna fix my shrimp posture rn 💪 stand tall king/queen, ergonomic awareness activated 🙏 healthy spine journey | I'm working on my posture. |
| his autocorrect fail in the gc is sending me 💀 | His autocorrect fail in the group chat was hilarious. |
| slop | Low-quality internet content, particularly that which was created by generative artificial intelligence. |
| No time for games. This is serious business. 🤨 | I'm serious. |
| quiet cafe + coffee + book = peak chill vibes ✨☕️ perfect place to unwind & observe 🙏 solo date goals | I enjoy relaxing in a quiet cafe. |
| world lookin kinda fuzzy rn 🧐 blurry vision alert, need eye check maybe? 🙏 squinting hard | My vision seems blurry. |
| freestyling life and it shows | I don't know what I'm doing |
| Just chillin' at home, binge-watching my fave show, fr. | I'm just relaxing at home and watching my favorite show. |
| gotta regulate the feels on this one fr 🙏 manage emotions queen/king, dont let em run wild ✨🧘‍♀️ stay calm | This requires emotional self-regulation. |
| logic left the chat | This doesn't make sense |
| her mentorship is a reliable guidepost fr ✨🧭 steady mentor queen offers consistent support 🙏 valuable wisdom | She provides steady mentorship. |
| why this gotta take FOREVER?? 😩 process slow af for no reason, inefficient nightmare fr 🙏 speed it up pls | This process is unnecessarily slow. |
| quiet night in >>> goin out sometimes ✨🏡 cozy homebody vibes activate, recharge introvert style 🙏 peaceful | I enjoy quiet evenings at home. |

## Sample 20 Training-Readiness Decisions

| brainrot | original_normal | training_normal | action | reason |
|---|---|---|---|---|
| OK boomer | Pejorative directed toward members of the Baby Boomer generation, used to dismiss or mock attitudes typically associated with baby boomers as out of date. |  | drop | glossary_definition_too_long |
| Roman Empire | A random event, person, incident, or thing that fascinates or intrigues one to the point that one is frequently thinking about it. Originated in 2023 after influencer Saskia Cort encouraged her Instagram followers to ask their male partners how often they thought about the Roman Empire, to which many answered quite often. The term spread internationally and evolved to mean something that frequently occupies one's thoughts. It has also morphed into a joke about how often people think about/mention the Roman Empire. |  | drop | glossary_definition_too_long |
| Wilted flower emoji 🥀 | Commonly referred to as the "Wilted rose emoji," it replaces, or used in addition to, the broken heart emoji, also expresses disappointment, albeit often with humorous undertones. |  | drop | glossary_definition_too_long |
| brainrot | The state of losing touch with the real world as a result of consuming hyper-stimulating or chronically online content, especially when characterized by online buzzwords ("skibidi", "fanum tax", "rizz", etc). Derived from the idea that one's brain would "rot" from consuming too much stimulating, addictive or degenerate content. |  | drop | glossary_definition_too_long |
| caught in 4K | Refers to someone being indisputably caught doing something wrong or incriminating on camera or with evidence to prove it, referencing 4K resolution. |  | drop | glossary_definition_too_long |
| crine | Variant pronunciation/spelling of "crying," typically meaning crying & dying from laughter (equivalent to "dying of laughter" or "I'm crying"). Often used in phrases like "Son I'm crine". |  | drop | glossary_definition_too_long |
| flop era | Primarily used on TikTok and Twitter when a person is not getting enough likes and views and starts posting memes and putting text over it in hope of going viral. |  | drop | glossary_definition_too_long |
| gng | Used to refer to a close group of friends or as a casual greeting/address (e.g., "wassup gng" meaning "what's up, gang"). Can also mean "good night gang" in parting contexts, especially among gamers or online communities. |  | drop | glossary_definition_too_long |
| hawk tuah | An onomatopoeia for spitting or expectoration on a penis as a form of oral sex used by Haliey Welch in 2024. |  | drop | glossary_definition_too_long |
| iPad kid | Term describing Generation Alpha children who spend most of their time consuming content via a phone or tablet screen. The term was popularized in January 2021 after a 21-year-old TikToker criticized Millennial parents for allowing their children excessive screen time, saying, "I need everyone else in my generation to promise that we are not going to raise 'iPad children'.... You've been shoving media and screens in these kids' faces since birth." He concludes: "Gen Z isn't allowed to raise iPad kids." The viral video garnered more than 525 million views on TikTok. |  | drop | glossary_definition_too_long |
| jestermaxxing | A slang term referring to both internet subcultures such as incels, and to the practice of using extreme humor, comedic antics, or acting like a "clown" to gain female attention and attraction (see also Clavicular). |  | drop | glossary_definition_too_long |
| nugu | Relatively unknown, obscure, or new groups that have not yet gained significant recognition or popularity among the K-Pop fandom. |  | drop | glossary_definition_too_long |
| out of pocket | To act (or say something) crazy, wild, unexpected, or extreme, sometimes to an extent that is considered too far; or unavailable. |  | drop | glossary_definition_too_long |
| periodt | Used as an interjection to indicate that the preceding statement is final and that there is nothing more to be said about it; similar to the British term "full stop". Originated as "period" in the early 1900s, spread in the 2010s via the City Girls rap duo and Black Twitter, and entered into the mainstream by 2019. The addition of the T stems from a common trend in Black English where T is used as a replacement for D. |  | drop | glossary_definition_too_long |
| pick-me | Someone who seeks validation by trying to stand out, often putting down others in their gender or group to gain favor or attention. This is most commonly done by degrading one's self. |  | drop | glossary_definition_too_long |
| queen | A gay slang term for a homosexual male – it was once considered pejorative but has been completely reclaimed, and is often used in combination with other words to describe subcommunities. |  | drop | glossary_definition_too_long |
| skill issue | Refers to a situation where a person's lack of ability or proficiency is seen as the cause of their failure or difficulty in completing a task, sometimes used ironically. |  | drop | glossary_definition_too_long |
| touch grass | A way of telling someone to "go outside", usually after said person is believed to have been online for too long. Believed to have originated in 2015, before experiencing a resurgence in 2020–2021. |  | drop | glossary_definition_too_long |
| unalive | An algospeak based euphemism for the word "kill" or other death -related terms, often in the context of suicide. This word is often used to circumvent social media algorithms, especially YouTube and TikTok, from censoring or demonetizing content that involves death-related terms. |  | drop | glossary_definition_too_long |
| who is this diva? | An affectionate rhetorical question used to compliment people who positively embody diva -like qualities such as boldness, style, and/or confidence. Sometimes used with a purple heart emoji at the end. Originated from TikTok. |  | drop | glossary_definition_too_long |

## Sample 20 Training-Ready Pairs

| brainrot | normal |
|---|---|
| life's just a series of unfortunate vibes | Everything sucks |
| she taught herself braiding from tutorials self-taught and cracked at it | She taught herself to braid hair from tutorials. |
| I'm totally drained today, no cap. | I'm just feeling really tired today. |
| he dips at exactly 5pm every day no cap sigma behavior | He always leaves exactly at 5 PM no matter what. |
| her pep talk was fire it actually motivated everyone she slayed that | She gave the most encouraging pep talk. |
| can't yolo this decision fr 🙏 careful assessment needed, think it through ✨🧠 smart choices only | This decision needs careful assessment. |
| i'm proud of what i did today self W honestly | I'm proud of what I accomplished today. |
| wanna go see the pandas & stuff? 🐼 zoo trip maybe? fun day out fr 🙏 channel inner kid | Let's visit the zoo. |
| hip flexors tight from sitting all day 😩 gotta stretch em out fr, unlock mobility 🙏 desk job pain | I need to stretch my hip flexors. |
| Chillin' at home after a mad busy day. | I'm just relaxing at home after a long day. |
| I'm just tryna wrap up my homework before dinner, no cap. | I'm just trying to finish my homework before dinner. |
| that random act of kindness made my whole week faith in humanity restored W | The random act of kindness made my whole week. |
| his apartment is always spotless that's giving very organized sigma | His apartment is always spotlessly clean. |
| mood: uninstall society | I hate everything |
| she uses her pro skills to volunteer?? ✨ generous talent queen gives back expertise 🙏 admire that | She volunteers her skills. |
| bro wants farming to heal the earth fr 🌱🚜 passionate sustainable ag king cares bout soil 🙏 eco farmer vibes | He is passionate about sustainable agriculture. |
| bro just radiates funny energy 😂 talent king makes ppl laugh effortlessly 🙏 born comedian | He has a talent for making people laugh. |
| I'm just vibing at home, binge-watching some flicks. | I'm just chilling at home today, watching some movies. |
| nah he reps his team hard fr 💯 loyal af, always got their back 🤝 #squadgoals | He's loyal to his team. |
| the brand's social media team is actually funny their content slaps | The brand's social media team is surprisingly funny. |
