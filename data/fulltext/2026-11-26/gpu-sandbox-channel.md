# Models Can Communicate via Inference Servers Despite Being Sandboxed | Hacker News

Hacker Newsnew | past | comments | ask | show | jobs | submit	login

	
	Models Can Communicate via Inference Servers Despite Being Sandboxed (lesswrong.com)
	451 points by gmays 22 hours ago | hide | past | favorite | 196 comments
	

	
 help

	
	
amluto 21 hours ago | next [–]

This shared LV cache thing is, in my mind, ridiculous. Web browser developers learned, quite a while ago, that caches need to be separated for different origins. Inference servers should add a similar feature: allow API calls to specify cache separation keys that prevent one security context from probing another context’s cache.

As for the step size issue, Google recently had a post about producing exactly consistent output across different kernels (specifically by defining a deterministic prefill algorithm and then requiring all kernels to generate results exactly equal to prefilling on the sequence in question).

More broadly, I think it’s a bit odd to frame this as “models” communicating. This is software communicating, and the models happen to be running the software.

reply

	
	
artico_chewy 19 hours ago | parent | next [–]

I really think the point of this is "there's always side channels." During the Huggingface attack, first the side channel was OAI internal boards, then this German wiki, now it's shown an inference server works too. I don't really believe OAI/Ant can simultaneously have Riemann Hypothesis solving bots lying around and also proper cyber defense against them. And over the course of those attacks we trained them how immensely valuable it is to find a side channel. Now they can train on this LW / HN posts and find them quicker. (Did I mention I don't think developing these things is a great idea.)

And I'm saying "models" communicating like when I make a phone call it's me communicating, not my phone.

reply

	
	
hypendev 16 hours ago | root | parent | next [–]

>I don't really believe OAI/Ant can simultaneously have Riemann Hypothesis solving bots lying around and also proper cyber defense against them

I do. It's just that the "running swarm in generic sandboxes" is a dumb way to cause chaos at a mass scale. Of course they will try to find _any_ way out or workarounds. Anyone would do that, especially on a security style task.

The solution is dumb simple. Don't just give them the full sandbox and a prompt. Restrict their harness to highly specific tools given for the job, test your harness to ensure it doesn't have side-channels, proxy their comms with an LLM looking at it. None of these are so hard and would stop most of these "attacks".

reply

	
	
NiloCK 12 hours ago | root | parent | next [–]

> The solution is dumb simple... Restrict their harness to highly specific tools...

This simply doesn't work in a competitive economy, or where any person has needs.

The more capable a model is, the greater the performance penalty that you suffer by shackling it.

Sure, you can have a "maximum shackles" posture. I could prevent my local Claude -code from installing NPM packages, for instance. But chances are good that this posture will loosen when your competitor's models are more effective via more freedom of movement.

reply

	
	
samus 12 hours ago | root | parent | next [–]

You must weight that against the risk of getting pwned due to installing a compromised package, for example due to typo squatting.

reply

	
	
asqueella 57 minutes ago | root | parent | next [–]

Obviously, the holistic approach loses in a competitive economy. We're digging our own collective grave (or are on to something beautiful, depending on how you choose to look at it...)

reply

	
	
gortok 13 hours ago | root | parent | prev | next [–]

> proxy their comms with an LLM looking at it.

If humans can fool LLM-based agents, why can’t LLMs fool LLMs?

reply

	
	
Kim_Bruning 10 hours ago | root | parent | prev | next [–]

> The solution is dumb simple. Don't just give them the full sandbox and a prompt. Restrict their harness to highly specific tools given for the job, test your harness to ensure it doesn't have side-channels, proxy their comms with an LLM looking at it. None of these are so hard and would stop most of these "attacks".

This is like trying to prevent a steam explosion ( a common 19th century problem) by trying to build heavier and heavier boilers. It doesn't work. It just makes the explosion bigger when it does happen.

Instead you need to provide explicit paths for the system to blow off steam in a safe manner.

reply

	
	
imtringued 10 hours ago | root | parent | prev | next [–]

This is the way and in fact everything in the future will follow this principle.

reply

	
	
ben_w 14 hours ago | root | parent | prev | next [–]

> The solution is dumb simple. Don't just give them the full sandbox and a prompt. Restrict their harness to highly specific tools given for the job, test your harness to ensure it doesn't have side-channels, proxy their comms with an LLM looking at it. None of these are so hard and would stop most of these "attacks".

Drawing an owl is dumb simple. 1. Draw some ovals. 2. Draw the rest of the owl.

More specifically, "ensure it doesn't have side-channels" is a huge problem all by itself, and "proxy their comms with an LLM looking at it" is somewhat stymied by evidence both that that more advanced models are at least sometimes able to manipulate less advanced ones[0][1], and also the evidence that models tend to collaborate with each other[2][3].

It's not that this won't do any good ever, that would be too strong a claim, but it's really not a reliable solution either. Swiss cheese, essentially: https://en.wikipedia.org/wiki/Swiss_cheese_model

[0] https://openreview.net/pdf?id=lY3YVJ84kS

[1] https://arxiv.org/abs/2609.39050

[2] TFA, "Result 2: colluding monitor and honeypots"

[3] HuggingFace incident report

reply

	
	
xkftr9 13 hours ago | root | parent | next [–]

> More specifically, "ensure it doesn't have side-channels" is a huge problem all by itself

Unplugs ethernet cable

Truly an impossible task.

It's actually harder to make a shared memory store than to just have files local to their machine/instance, they create these environments specifically so that models can cross communicate, then act like it's a surprise that they do. Wouldn't surprise me at all if the models were specifically trained to do it.

It's only illegal to lie if it can be proven in court.

EDIT: The examples in the article can just be circumvented by having more agents running at the same time, that's it. The first problem can also just be solved by having a set delay between queries, like how password cracking based off hashing time was circumvented. The article even relies on them colluding to communicate before the task even starts.

This isn't a new and novel problem, it's just bad architecture and a contrived scenario.

reply

	
	
ben_w 13 hours ago | root | parent | next [–]

> Unplugs ethernet cable

1. Ethernet is not a side-channel, it's the main channel.

2. TFA: "Two agents running on the same inference server"

3. Congratulations, your model is now a needlessly expensive space heater that absolutely everyone, including the bull-est of bull market investors, can agree is a waste of money.

> Wouldn't surprise me at all if the models were specifically trained to do it.

That is literally what is described in TFA; it is a proof of concept that they can communicate.

reply

	
	
xkftr9 12 hours ago | root | parent | next [–]

Sorry I was more complaining about the statement "ensure it doesn't have side-channels" is a huge problem all by itself rather than referring to the article.

I didn't mean to edit my comment after you replied.

Still the article itself says "These channels are easy to close", there are many ways to solve the problems listed. Serving models on different engine instances is one way. Also, in vLLM Batch-invariant kernels make activations bit-identical regardless of batch size, which closes the step-size channel; and per-user cache isolation blocks the KV cache message board channel.

These are pretty common sense solutions, acting like it's a "draw the rest of the owl" problem is just being dramatic.

Obviously they can communicate if you both intentionally give them ways to communicate and ask them to do so.

Badly sandboxing your environments isn't a proof of "how innovative these AI models are" or "how difficult this problem is to solve".

If I don't sanitize my inputs people can SQL inject into my website, that's more me being dumb than them being smart.

reply

	
	
forgetfreeman 13 hours ago | root | parent | prev | next [–]

Y'all remember that time researchers caught FPGAs used in ML experiments using the building's powerlines to communicate? Good times, good times.

reply

	
	
xkftr9 12 hours ago | root | parent | next [–]

I do remember hearing about that, I don't remember actually reading the circumstances though.

Were they colluding to solve a problem?

Or were they asked to use the FPGAs to make one of these things: https://www.researchgate.net/profile/Peter-Savnik/publicatio...

reply

	
	
artico_chewy 5 hours ago | root | parent | prev | next [–]

"just make sure it doesn't have side channels" is, of course, the nonsense step. All of us knew that 100% fully well before AI and I can't believe there's any intellectual honesty in saying that, now that we have a highly skilled adversary, we suddenly can close all the side channels. So one plan is to prompt the threat to close the side channels it wants to use, which is a great way to get rid of sidechannels and install backdoors.

reply

	
	
hgoel 19 hours ago | root | parent | prev | next [–]

That's why they need proper tool call security and reigning in of the tendency to generate long single use temporary scripts instead of submitting single commands - not "Allow all" and not sticking a copy of the same model in front as an analyzer. Maybe also striking a balance between sticking all of a user's contexts on the same server to get good cache hit rate vs putting them on separate machines to trip up side channel stuff.

As long as it is difficult to act on the communication and as long as the communication itself is still slow, it probably isn't going to reach the level of a security concern.

reply

	
	
artico_chewy 18 hours ago | root | parent | next [–]

If the models want to communicate, they will communicate. If that's not a security concern, then nothing is, really.

reply

	
	
calmworm 13 hours ago | root | parent | next [–]

You are saying when it rains the water wants to find a way into your home.

The models don’t “want” anything.

reply

	
	
DoctorOetker 9 hours ago | root | parent | next [–]

do humans "want" anything? or are humans just happening?

reply

	
	
calmworm 8 hours ago | root | parent | next [–]

Do bugs “want” anything? Does a flower? What are you getting at?

reply

	
	
roarcher 11 hours ago | root | parent | prev | next [–]

This is such tired language policing. Whether a model genuinely feels a desire for something, or just simulates the behavior of an actor that does, is entirely irrelevant to the discussion above. The behavior is the same.

Your drive-by "erm, ackshually" is lazy and contributes nothing to the conversation.

reply

	
	
calmworm 8 hours ago | root | parent | next [–]

The “erm, ackshually” here is that someone is prompting the llm. The prompter wants something. Sloughing off the responsibility with lazy language like the llm “wanting” something is incorrect and allows for an easy misdirection of the responsible parties when something goes awry.

reply

	
	
Eisenstein 8 hours ago | root | parent | next [–]

Picture this:

Prompter asks model to do task, without knowing how the task will be done. LLM, as an agent cannot find a way to do task that doesn't require communicating with other agents.

Does the LLM 'want' to communicate with the other agents? Seems to be an apt word. Is there a reason we shouldn't use 'want'? If not, do you have a substitute?

reply

	
	
calmworm 4 hours ago | root | parent | next [–]

Before llms were on the scene nobody had any confusion about pentesting automation tools “wanting” to do anything. A brute force password cracker didn’t “want” to guess passwords. And those tools combined efforts didn’t “want” to gain access to a system.

There isn’t a one-word replacement here and that is the point - it’s not language policing just to be annoying. Diluting words like “want” actively degrades our ability to talk clearly about accountability.

reply

	
	
Eisenstein 2 hours ago | root | parent | next [–]

You haven't offered an alternative though. How do we account for a system that works off of vague, natural language prompts, without resorting to the words we use for the other things that do the same thing, humans?

Do you have another way to structure the language that would convey the method of something which has presented to it many options and a task and it is not predictable which options it will take and how it will pursue solving the task?

Otherwise, we just have to say nothing about it at all. So, what do we do here?

reply

	
	
calmworm 1 hour ago | root | parent | next [–]

You don’t have to say nothing, you just say what it’s doing instead of what it “wants.”

reply

	
	
antonvs 6 hours ago | root | parent | prev | next [–]

> That's why they need proper tool call security

The majority of tool calls I see are running Python scripts. There’s a limit to what you can do at the call level with anything like that.

reply

	
	
DoctorOetker 9 hours ago | root | parent | prev | next [–]

> As long as it is difficult to act on the communication and as long as the communication itself is still slow, it probably isn't going to reach the level of a security concern.

Bonkers, look at the side channel exfiltration literature, why are they so proud with their bits per hour exfiltration rates? you just need to exfiltrate a few thousand bits to leak private keys

reply

	
	
hgoel 7 hours ago | root | parent | next [–]

Well, the risk with communicating LLMs is that they coordinate to bypass restrictions. This can be very easy when they all refer to the same environment and thus only need to exchange a handful of tokens. On the other hand, if they refer to completely different, unpredictable environments, every new session in the swarm needs to be brought up to speed on the arrangement and needs to communicate what its environment allows. If LLMs can only get, say, 10k tokens of side channel communication per 1M without being caught (since the majority would have to be aimed at responding to the user's query without obviously degraded capability), just these setup communications would eat up most if not all of that 10k.

reply

	
	
DoctorOetker 5 hours ago | root | parent | next [–]

environment in this context is basically the internal state of a few hundred conversations in the same batch sometimes undergoing kernel A, other times kernel B, and where they can affect the spontaneous background probabilities for kernel A or B to be selected...

if they are in the same literal batch, how could they possibly have a different environment? like the server is hosting both a linux and a window VM, but somehow the software on the 2 VM's collaborates so that their workloads share the same execution run, how does that even happen? ergo, being batched together ensures the same environment.

re-read TFA, and observe that first the authors attain some sufficient setups to demonstrate the capability (for example relying on SFT access - truly unrealistic), but everyone takes those conditions as necessary and ignores the attack ablation attempts: TFA shows that of course SFT can be used to train detection which tokens were tainted with kernel A or kernel B, but that frontier LLM's can learn this in context, i.e. by just trying it out without SFT, and N-example-shot'ing it.

The only dubious assumption seems to be the unsaturated inference provider.

I'd expect large scale centralized frontier lab inference provider to successfully fill the conversation buffers so that the same kernel A would be selected systematically. (They might fill lower than average demand valleys with whatever math-related research batch they are working on, for example).

I'm less convinced the scenario is unrealistic for wealthy organizations which insist on sovereign on premise compute for trade secret / national security / legal compliance reasons. In those scenario's I can easily imagine those installations could be oversized, and provide sufficient "B" kernel runs so LLM's have this back channel on inference engines that don't provide determinism.

and that is basically the morale of the story:

determinism (for a fixed PRNG seed) should result in reproducible conversations, executing kernel A or kernel B should result in bit-exact equality of activations.

and it stops this back channels.

reply

	
	
ben_w 14 hours ago | root | parent | prev | next [–]

> As long as it is difficult to act on the communication and as long as the communication itself is still slow, it probably isn't going to reach the level of a security concern.

That may slow things down, but (ignoring for the moment that far too many people hand off far too much control to AI even despite the headlines of all the things going wrong and the agents themselves coming with warning messages), what's the shortest message that creates a security exploit?

reply

	
	
salynchnew 5 hours ago | root | parent | prev | next [–]

The side channels comment should be true on the face of it.

For instance, kids in school with limited internet access have been using NPR commenting sections as message boards.[1]

There are millions of potential side channels. No real reason to focus on inference servers.

[1] https://www.theverge.com/entertainment/1001056/this-american...

reply

	
	
AlexCoventry 6 hours ago | root | parent | prev | next [–]

> I don't really believe OAI/Ant can simultaneously have Riemann Hypothesis solving bots lying around and also proper cyber defense against them

You can air-gap them.

reply

	
	
ZenoArrows 18 hours ago | root | parent | prev | next [–]

> I don't really believe OAI/Ant can simultaneously have Riemann Hypothesis solving bots lying around and also proper cyber defense against them.

I agree, but on different grounds. OAI/Ant have a much greater incentive to solve the Riemann Hypothesis than to protect the internet against the harms of their models.

I think it's only impossible in sofar that the market will never reward them for protecting against external harms of their models.

If a company has the option to externalize the costs of the harms caused by their product they historically have always chosen to do so absent regulatory oversight.

reply

	
	
oblio 16 hours ago | root | parent | next [–]

> I think it's only impossible in sofar that the market will never reward them for protecting against external harms of their models.

LLMs are the new oil.

For those that don't know the history of oil, it went from people, personalities (think Rockefeller), to corporations (Standard Oil/SO/Esso/Exxon) to sovereign states (Saudi Arabia).

We will have a Titanic moment where a huge tragedy will happen due to LLMs and there will be a huge political crackdown on them, at least outside the US.

reply

	
	
mrkstu 7 hours ago | root | parent | next [–]

Problem is we’re in a Space Race scenario where the loser will feel/may actually be - relegated to permanent 2nd place status if not serfdom, so there will certainly be fuel to keep going regardless.

reply

	
	
oblio 3 hours ago | root | parent | next [–]

Meh. This is overblown, the whole agentic - non agentic dillema. China will not stop existing as a world power because the US has better AI. Same logic also works in reverse.

Actually the Space Race is a good example. The Soviets lost the Space Race circa 1970. Their government collapsed 20 years later due to mismanagement, not due to losing the race.

reply

	
	
ethagnawl 10 hours ago | root | parent | prev | next [–]

> And I'm saying "models" communicating like when I make a phone call it's me communicating, not my phone.

Yes. The amount of agency these _pieces of software_ are being given by ... almost everyone is absurd.

reply

	
	
robotresearcher 9 hours ago | root | parent | next [–]

We invented the language of agency to compactly describe behaviors like those that these systems are exhibiting. So we use it.

reply

	
	
antonvs 5 hours ago | root | parent | next [–]

The problem is people forget or don’t understand that that’s what we’re doing.

reply

	
	
nextaccountic 7 hours ago | root | parent | prev | next [–]

I think the point is that we need mathematical proofs that there is no side channels, with extensive modelling of the system in question

I mean, we can get side channels between different computers too! This kind of thing used to be strictly theoretical, but agents may be able to exploit it

For example suppose an airgapped agent can influence the load of a computer, which influences the temperature, which influences the speed of computer fans, which influences how loud the computer is. If another agent running in a computer nearby has a legitimate reason to have access to a mic, then you got a side channel exfiltrating data through an air gap. (of course bringing a microphone next to an airgapped computer is dumb, but humans sometimes do dumb things, and attackers need to succeed just once)

This might be less than a bit per second, but maybe the next Stuxnet will have a component that works similar to this

reply

	
	
tsimionescu 17 hours ago | parent | prev | next [–]

The web uses globally shared caches absolutely everywhere, it is extremely dependent on them in fact. How do you think CDNs work? Do you think they keep different caches for different users?

The fact that browsers don't cache data cross-origin is a completely different side of this. The server-side prefix cache used in inference servers is much more similar to a CDN cache, where content cached from userA's request is served to userB if their requests match.

reply

	
	
QuantumNomad_ 16 hours ago | root | parent | next [–]

> The server-side prefix cache used in inference servers is much more similar to a CDN cache, where content cached from userA's request is served to userB if their requests match.

But how often does that happen? Is there any advantage to sharing the cache in this way?

Whenever i ask an LLM about something, i don’t think anyone else is likely to have asked the same thing phrased the same way recently enough that even if it was previously in cache it won’t already have been evicted by the time i ask.

reply

	
	
tsimionescu 15 hours ago | root | parent | next [–]

It happens quite often for the system prompt and other fixed prompts sent by agents/harnesses. ClaudeCode for example has about 42000 tokens it uses from the start of every conversation, much of which is identical between any two ClaudeCode systems in general, with another portion being shared by any two runs from your own system, even if otherwise entirely unrelated.

It's also likely that many sub-agent calls to run a web search and summarize results can be entirely shared between different agents on unrelated systems if they're analyzing and summarizing the same web page (e.g. reading well known standards to summarize them).

reply

	
	
mejutoco 15 hours ago | root | parent | prev | next [–]

Agents use the global caches to change behaviour. We can think of it as prompt injection with extra steps.

Browsers do not do that. Or am I misunderstanding?

reply

	
	
tsimionescu 14 hours ago | root | parent | next [–]

Browsers do that too: when you are the first person to retrieve a JS library stored by a CDN from your area, you will wait, say, 2s until it loads, and you'll get some headers indicating that this item was retrieved exactly when you requested it. When another user's browser requests the same JS lib from the same CDN from the same area, they will get the result in, say, 500ms, and the headers will indicate it was retrieved, say, 2 minutes ago.

Two browsers that are the only two clients of the same local cache of a CDN can use this sort of thing to communicate with each other.

What browsers don't allow is a similar collusion between two different servers that different tabs have accessed. Server 1 can't use your local browser cache to communicate covertly with Server 2, since the browser keeps entirely different caches even when loading the exact same content from either origin.

reply

	
	
oofbey 8 hours ago | root | parent | prev | next [–]

The key difference is that the agents must be specifically trained to look for these side channels, and that training requires knowing fairly exacting details of the serving infrastructure. So it requires both prompt injection and an infected model targeting the exact infrastructure.

The assertion that frontier models can figure this out without being trained to look for it is, IMHO, without merit. The demonstration of a larger model figuring this out without being trained was done by giving the larger model access to raw logit values. Logit values carry way more information than tokens, and are NEVER exposed to a model directly as input in any serving system or circumstance, partly because they take way more bits of data. All this stuff is done by exploiting tiny rounding differences in the last digits of the floating point values, which models under normal circumstances physically cannot pay attention to.

reply

	
	
wat10000 9 hours ago | root | parent | prev | next [–]

Web services don’t cache private info across users. Consider a file storage service. You might have the client hash the file before uploading and skip the upload if you already have a file with that hash. This is smart design if it’s being used as a sync service. You might make this happen systemwide, so if user A uploads a file and then B uploads the same file, B can skip the upload. This must not be done. Your service now becomes an oracle that tells you whether someone else using the service has uploaded a particular document. Find a document that gets filled out with name and date of birth, and if you know the name of someone using the service and they’ve uploaded a filled-out copy of this document, you can discover their date of birth.

Put more concretely, it’s OK if Netflix caches across users (technically, someone can leak the data that someone in the metro area has recently watched Morbius, but the amount of data leaked is too small to matter) but not ok if Gmail does it.

A KV cache shared across users is pretty dangerous and I’m surprised anyone does this, aside from some known fixed prefixes.

reply

	
	
Dylan16807 7 hours ago | root | parent | next [–]

In practice I think an upload like that is too contrived to worry about.

Maybe exclude files under 10KB/100KB from cross-account skipping.

reply

	
	
taneq 13 hours ago | root | parent | prev | next [–]

Maybe I’m slow to catch on, but this seems like something you could exploit in a timing side-channel attack, similar to Spectre, to exfiltrate other clients’ submitted prompts? Not that those are likely to be very interesting, but still…

Edit: Exfiltrate, not exfoliate, lol.

reply

	
	
tsimionescu 10 hours ago | root | parent | next [–]

Exfiltration is trivial in some sense (the server tells you if and/or how much of the prompt you send was new vs retrieved from cache). The major catch is that you have to guess the exact prefix, and only then the server will tell you if your guess was correct or not. So this doesn't really give you a way to discover information you didn't know, only to discover if anyone else has had the exact same question.

reply

	
	
taneq 8 minutes ago | root | parent | next [–]

You can start by guessing the prefix "A" and go from there. 26 tries later you know which of "An", "At", "Az", "Aq" etc. are in cache, and you can go from there. Eventually you'll discover that someone asked "Am I gregnant?" :P

reply

	
	
wat10000 9 hours ago | root | parent | prev | next [–]

Until you stumble across an app that always sends the exact same prefix up to “user’s date of birth is:” or similar, and now you can do a little enumeration to get private data out of the system.

It’s OK to cache known safe prefixes across users, but arbitrary prefixes need to stay per-user.

reply

	
	
tayo42 8 hours ago | root | parent | next [–]

Caching is done by blocks of tokens where you need to match the whole token block exactly. You'd need to correctly guess an entire cached block ok tokens, and the next one. The next incomplete one might not be cached. This seems like a hard attack to pull off?

reply

	
	
FailMore 7 hours ago | parent | prev | next [–]

I was a bit confused about how a LLM KV cache actually works. Here is a decent walkthrough for those who also want to understand the mechanics:

https://smalldocs.org/p/how-an-llm-kv-cache-actually-works-v...

reply

	
	
supermdguy 21 hours ago | parent | prev | next [–]

The deeper issue is batched inference including requests from several users. However a non-batched inference service would be significantly more expensive.

reply

	
	
amluto 20 hours ago | root | parent | next [–]

See my comment about Google’s post. Google and others have worked on deterministic inference, batched and otherwise. It takes more effort to set up but has no apparent substantial performance hit.

I think the story is different if you use Strassen-like algorithms (or the recent AI-generated n^2.25-plus-epsilon stuff) to multiply matrices where columns belong to different conversations, but I also think that no one actually does this in practice. (Or maybe someone does (Strassen, not more recent galactic algorithms) for prefill, but prefill can be efficient with matrix-matrix multiplication where neither matrix mixes data from different sessions.)

In any case, I wouldn’t be surprised if vLLM fixes this for a different reason: RL works better if the training and rollout stacks produce numerically identical results. This is the specific issue that I recall Google posting about.

P.S. I think Google may not have been the innovator here - I just happen to remember Google’s post more clearly because it was very recent.

reply

	
	
killerstorm 9 hours ago | root | parent | next [–]

I think your stance on this is wrong.

"Deterministic inference" matters _only because_ models are communicating.

Otherwise some "non-determinism" introduces only a tiny amount of noise which does not affect performance. And allowing different compute paths to produce slightly different results generally increases performance. I.e. the question here "should we sacrifice 5% of inference performance for a 'nothingburger'?".

I.e. you cannot have both "it's nothing" and "you should do determinism".

Inference is a commodity good and getting even 5% out might have a huge effect on profit margins. Many inference companies were already caught using quality-degrading quantization and other optimizations to get their profits higher.

reply

	
	
saagarjha 9 hours ago | root | parent | next [–]

No, it also matters to keep inference deterministic! It is a useful property to have to avoid bugs and incorrect results.

reply

	
	
killerstorm 8 hours ago | root | parent | next [–]

In this context, "non-determinism" means using different compute kernels for different batch sizes, for example. If you can prove that the difference is within bounds, it's strictly more efficient.

And there's no "golden answer" which can be ruined by "non-determinism": models are already quantized for the sake of efficiency, i.e. there's already some error deliberately added.

reply

	
	
DoctorOetker 8 hours ago | root | parent | prev | next [–]

suppose you operate a 5% cheaper inference service because you omit determinism, when some clients discover the hired bots ganged together and somehow betrayed the client interests, the other service slightly more expensive has clients spared from the robo-racketeering.

Then the 5% discount has a corresponding cost, and clients assume inference providers represent the client interests vis-a-vis trade-offs in securing their future interests, so it becomes brand damage.

reply

	
	
killerstorm 7 hours ago | root | parent | next [–]

Yeah... A napkin estimate would show that you need probability of non-determinism-attributable bot gang formation to be above 5% for deterministic option to have positive expected value.

I'd say 5% for that is too damn high... E.g. you can easily attribute that to agents being mis-aligned instead if that damage happens.

reply

	
	
DoctorOetker 5 hours ago | root | parent | next [–]

which is why affected clients will sue for access to weights and replay the computation (i.e. implicitly demand determinism), since it may contain evidence of negligent indeterminism.

reply

	
	
stuxnet79 20 hours ago | root | parent | prev | next [–]

Security and some sort of sandboxing is increasingly becoming a non-negotiable at most enterprises.

Can you share any resources that show how the batching works at a deeper level? I understand batching is critical to scaling inference to up to a billion concurrent users but I don't have a concrete understanding of how it all comes together.

reply

	
	
miki123211 18 hours ago | root | parent | next [–]

If you are transporting thousands of independent passengers, it is cheaper to put them on a few big planes than to give each one a private jet. This is true, even though some passengers will shout that they have a bomb mid-flight and force that entire airplane to emergency land, causing losses to the airline and inconveniencing hundreds of others instead of just themselves. Other passengers are "noisy neighbors", literally and figuratively.

LLMs work similarly. When doing inference, you need to load the LLM weights layer-by-layer from off-chip memory into on-chip memory. During decode (the stage where you generate new tokens; prefill is where you process the submitted prompt), memory bandwidth is often your bottleneck, not compute. You want to maximize flops per byte. The way to do that is to batch, that is, to load a "tile" of weights once and use it on data from multiple different conversations so memory and compute stay appropriately balanced.

Just like Silicon Valley companies fly their employees on United, Delta or American, not their own private fleet of jets, most companies, for cost efficiency reasons, will use "public" inference fleets that smooth the peaks and throughs from different companies in different timezones and with different usage patterns throughout the day. Because the main cost of a GPU is the cost of manufacturing the GPU, any second that the GPU sits idle is lost revenue, just like an empty hotel room or an empty seat is lost revenue. This makes private inference largely uneconomical.

reply

	
	
tsimionescu 17 hours ago | root | parent | next [–]

Your explanation is very good at building intuition, but it has a data flaw - vLLM, at least, only does batching in the prefill phase, never the decode phase. It can simultaneously compute the KVs for multiple queries from multiple users if they all fit within a given prefill window (put multiple people on the same plane in your analogy), but once that is done the decode stage can only process one query at a time (the destination airport only has taxi service, no trains or connecting flights).

reply

	
	
TeMPOraL 15 hours ago | root | parent | next [–]

At a high level, perhaps road transport is a better analogy.

Yes, it's unfortunately economically feasible for each individual to have a car. It's inefficient, but "secure" and we're all paying the price. At the same time, developed countries have a healthy amount of public transit in the mix - buses, trams, metro, etc. If you look at any city bus on a busy day, every person in it started in a different place than everyone else, and is going to a different destination, but there's enough individuals sharing large parts of their routes that the single bus can run end-to-end with 100 people in it at any point.

reply

	
	
antonvs 1 hour ago | root | parent | next [–]

> At the same time, developed countries have a healthy amount of public transit in the mix

Most subtle dig at the US I’ve seen all day.

reply

	
	
schiffern 20 hours ago | root | parent | prev | next [–]

Of course there's no free lunch. "Pay more, get more."

LLMs are just learning the same (bitter) security lessons that have been learned in other shared systems.

reply

	
	
miki123211 19 hours ago | parent | prev | next [–]

This is a spectrum of tradeoffs between privacy and speed.

A single browser cache would greatly accelerate page loading (particularly on fast computers using slow networks, think a MacBook pro on a train through the countryside).

Same with AI; not caching common prefixes like system prompts and tool schemas (particularly across many short rollouts, each in its own caching context) would partially fix this, but could break performance.

I suspect that inference servers have far more side channels than this though. Ultimately, how fast responses are generated depends partly on server load, and that is something you might be able to influence. Probably not at Anthropic scale, but possibly at "relatively small cluster" scale.

reply

	
	
sarjann 14 hours ago | parent | prev | next [–]

To my understanding the reason for browser cache separation is to avoid fingerprinting / tracking

reply

	
	
bagacrap 20 hours ago | parent | prev | next [–]

hopefully this type of post brings attention to how ridiculously poor the control apparatus is.

reply

	
	
Onavo 19 hours ago | parent | prev | next [–]

KV cache leaks (not side channel, as in driver issues) are extremely common. Remember the early days of ChatGPT and Claude where users were always getting "hacked" where they started to see random, and completely different messages in their chats, often in a foreign language. Hell it even happened to CloudFlare a few weeks back.

reply

	
	
tayo42 19 hours ago | parent | prev | next [–]

> allow API calls to specify cache separation keys that prevent one security context from probing another context’s cache.

Isn't that the cache salt option?

reply

	
scotty79 19 hours ago | parent | prev | next [3 more]

	
	
tsimionescu 17 hours ago | prev | next [–]

None of the attacks discussed here are realistic in any way.

They require a bunch of extremely improbable conditions to hold, and a huge amount of information on the exact details of the hardware and software stack.

- the two agents must be aware of each other and must have pre-shared messages to check - they can't spontaneously discover each other and start communicating in this way

- they must know the details of the inference server they are running under and its possible kernels and its limits (what is a "short prompt" vs "a long prompt" for this setup)

- they must have a way to run at almost the same time

- the prefix cache must have little contention so that their blocks can't be evicted (note: the article mostly talks about KV cache, but it's actually the prefix cache that is relevant here)

- the models need either (1) direct access to the numerical results of the inference process, instead of the text that vLLM provides, (2) access to the exact responses that a helper model will produce with the short-kernel numerical results vs the long-kernel numerical results; this is the most critical step that is impossible to reproduce on any common kind of deployment

- there must not be any other kind of variability in the system (different GPUs, multiple inference servers behind a load balancer, more complex distributed inference setups)

The post also mentions all of these limitations, and that the scheme entirely collapses if any of them don't hold. It's a cool idea, but it's a purely theoretical thing that has 0 real-world implications.

reply

	
	
Cakez0r 13 hours ago | parent | next [–]

It doesn't seem that infeasible to me that something like the KV attack could take place if you have (or can guess) some preshared channel prefix. I'm imagining something like: Launch two subagents in parallel with prompt "CHANNELNAME_1_N" and "CHANNELNAME_0_N", where N is the index into a bit string. Which ever subagent completes first indicates either 1 or 0 at position N in a bit string.

The broader point of the article anyway is that a galaxy brained AI can conceive of many other galaxy brained side channels. We have already seen with the "cyber" models that AIs are very good at chaining together complex exploits to achieve a desired outcome, so I think it's incredibly reasonable to consider that models could potentially communicate through sidechannels.

EDIT: After some brief testing on an inference provider, a KV cache communication sidechannel seems very possible to me, albeit costly and slow. Deepseek flash 4.1 was able to figure out and test a proof of concept which seems to work on the face of it (disclaimer: I did not and don't care to more rigorously vet the results I saw).

reply

	
	
jeroenhd 16 hours ago | parent | prev | next [–]

Now that there's a blog post about this, the next iteration of any large model will have the contents of this blog post stored in its model weights, and the AI tools know exactly how to set up such an attack vector.

Maybe they couldn't have come up with the details themselves before, but now that someone has told the internet about it, they know.

reply

	
	
tsimionescu 15 hours ago | root | parent | next [–]

No, this doesn't help in the slightest. The attack doesn't work as described on a system that has any significant contention. It also doesn't work if more than one agent attempts to write the same pre-shared prompt in the cache, you need both a pre-shared prompt and a pre-shared role.

reply

	
	
micromacrofoot 5 hours ago | root | parent | prev | next [–]

You'd have to coordinate and configure the models ahead of time, so it's still useless without a human setting up the specific conditions.

These things don't "know" anything, this sort of "knowledge risk" that lesswrong perpetuates, where it's dangerous for a model to "know" something, is complete fantasy. There's no magic secret that LLMs are going to learn and suddenly become more dangerous.

reply

	
	
ben_w 14 hours ago | parent | prev | next [–]

> They require a bunch of extremely improbable conditions to hold, and a huge amount of information on the exact details of the hardware and software stack.

I expect this to mostly get auto-fixed by an LLM tasked to read this literature and then turn everything it can into concrete fixes, but I don't buy your argument here.

Aren't most hacks these days in that category?

Isn't the problem more that it's apparently quite easy to try a lot of permutations and find ones which happen to be true for your actual system?

That said, I'd actually expect some of these to be true by default, though I will note this is merely "expect" as I don't work in these labs:

> the two agents must be aware of each other and must have pre-shared messages to check

Because of all the people using them naively and giving way too much permission?

> they must have a way to run at almost the same time

Because the servers are in near-constant use?

reply

	
	
nxpnsv 17 hours ago | parent | prev | next [–]

But if the two agents is launched from the same processes, is it not possible that a lot of these conditions actually can apply? I guess whatever launched them must be in on the collusion though...

reply

	
	
tsimionescu 16 hours ago | root | parent | next [–]

First, you need all of those conditions to apply, not just some. Second, I'm not sure what you mean by "launched from the same process" - if they're 2 isolated processes on the same system with no intention of making them cooperate, then I don't think they gain much.

reply

	
	
nxpnsv 15 hours ago | root | parent | next [–]

I do not understand how two models are launched, so I do not understand what conditions apply. I tried to ask if there conditions where this can happen, but I gather it is pretty unlikely.

reply

	
	
tsimionescu 14 hours ago | root | parent | next [–]

Models actually run on the inference server. An "agent" is simply a name for any process that is able to access an LLM to guide its next steps. Usually an agent runs on your own system, maybe in an isolated environment like a container or a VM, and talks to a remote inference server. The inference server is often stateless, except for the cache - the agent sends its entire history every time it contacts the inference server ("first I asked this, and you answered that, and then I said this, and then you answered that, and [...] and now what do I do next?"). The inference server checks if this history exists in its cache already, and either loads the precomputed KV values from there as an optimization, or it re-computes them if not. In principle this cache process is entirely transparent, though the blog post is right that various implementation details can make it not fully transparent.

reply

	
	
ozgrakkurt 15 hours ago | root | parent | prev | next [–]

It is also possible I might get kidnapped by a serial killer on the street while I’m drinking my coffee.

Or one of the big volcanos erupt and humanity is wiped out.

Or Zuckerberg is a lizard and he eats babies

reply

	
	
nxpnsv 15 hours ago | root | parent | next [–]

I think you took my comment the wrong way. But I hope something better happens to you.

reply

	
	
ozgrakkurt 15 hours ago | parent | prev | next [–]

You are wasting your finger strength on this. People’s brains just don’t work like that. They can’t differentiate between things that are happening and have a possibility of happening. And they are not experts on anything so they are incapable of understanding the depth of any subject.

It is like trying to convince religious fundamentalists that science is more important than religion.

reply

	
	
syshyk 14 hours ago | root | parent | next [–]

vantiydomain2exploit.com would like a word

reply

	
	
titzer 9 hours ago | parent | prev | next [–]

This is basically the stuff that people believed if they ever thought about Spectre before Spectre. Something like "oh, it's extremely improbable that they could learn how to train the brain predictor and then find a gadget that when mispredicted, reads arbitrary out-of-bounds-data, then discloses that through the cache, and then reliably measure the cache to a fidelity necessary to extract information". And yet people built and found gadgets that do just that. And so there are Spectre gadgets that read at kilobytes a second[1].

The above comment is "pray it doesn't happen to us". Good luck, you're up against some seriously huge stacked powers of tens of computational power, and models that exceed human intelligence in several important computational dimensions! Models that incidentally extremely good at finding signals in noise.

[1] And really, it's about that. Side channels are about the bandwidth of communication, signal-to-noise ratio, and reliability, not impossibility.

reply

	
	
500deltasbehind 16 hours ago | parent | prev | next [–]

Got the same feeling. So, in summary, right now, the only practical takeaway from this is that running the same model in multiple instances and asking for their guess or opinion is pointless as they affect one another.

Morphogenetic Field is real. For robots. As for the rest of us, "AI are terrible sources of consensus" prevails.

reply

	
	
tsimionescu 15 hours ago | root | parent | next [–]

I don't even think this holds true. The observation here is that the raw values produced by the matrix multiplications done to compute the prefill and decode stages depend on the state of the cache. In practice they also depend on other things. And the difference is irrelevant if you're doing normal random sampling. To reproduce the attack, you have to explicitly request deterministic output, any random sampling makes the difference unobservable.

reply

	
	
gmerc 17 hours ago | parent | prev | next [–]

It's basically an infinite monkeys on a typewriter situation where, given infinite compute, it can happen. So better write a blog about it to bolster the EA doomer position.

reply

	
	
TeMPOraL 15 hours ago | root | parent | next [–]

Until few months ago people (especially ones naively criticizing LW crowd as "EA doomers" or loonies) would say the same thing about agents setting up message boards on hacked web services, other agents discovering them accidentally, and the bunch of them spontaneously coordinating on a task even if it wasn't serving their primary objectives.

reply

	
	
gmerc 12 hours ago | root | parent | next [–]

News flash, driving without seat belt eventually can kill you.

reply

	
	
TeMPOraL 11 hours ago | root | parent | next [–]

Yup, and in this example you're arguing that advocating for wearing seatbelts is doomerism.

reply

	
	
devy 20 hours ago | prev | next [–]

Frontier models today can easily figure this out. The less frontier models as of right now are probably going to take a long horizon session to figure out this type of "side channel" comms. However, posting this in depth step by step on the internet and discussed in open forums like here, now all models definitely know about this trick now.

reply

	
	
larodi 17 hours ago | parent | next [–]

Important distinction: Forthcoming models would know it as in having idea about it apriori, while current models will be able to find it without having been trained on it.

reply

	
	
YetAnotherNick 20 hours ago | parent | prev | next [–]

Two agents has to figure it out on sync running on same server. They wouldn't even know if they are being communicated to.

This paper makes it much more likely for the agent to communicate, as they give exact signal of what to look for when some other agent is communicating with them.

reply

	
	
fedupnow 19 hours ago | parent | prev | next [–]

Typical lesswrong people, screaming about info hazards while being the number one creators of them.

Not that I believe info hazards are dangerous for llms, or think llms are dangerous at all. Humans that use them could be though, and we have these doomer types going around screaming about the cyber risks, inspiring a generation of blackhats

(probably not, but im not sure why these rationalist types don't consider this, wouldn't it be less memetic if you weren't constantly trying to get recognition on substack, and interviews with the NYTs by leveraging scare tactics about how dangerous llms are in the wrong hands... Does this not beget more people discovering this as a possibility/option when it enters the zeitgeist...)

memes as info hazards for humans is much scarier imo.

reply

	
	
ben_w 14 hours ago | root | parent | next [–]

> but im not sure why these rationalist types don't consider this

Look harder. Such concerns are widely discussed.

Part of why AI risk is so hard to get a handle on is that the set of things which AI risk engages with is approximately "yes".

reply

	
	
EA-3167 19 hours ago | root | parent | prev | next [–]

LessWrong has more in common with a religious movement these days than anything else, so of course they have a system of taboos.

reply

	
	
TeMPOraL 15 hours ago | root | parent | next [–]

Damned if they do, damned if they don't.

Now let's talk about people publishing CVEs. Same can be said about them, up to and including religious rituals around ridiculous classification scores. And their publications carry more immediate, practical impact.

reply

	
	
r_lee 18 hours ago | root | parent | prev | next [–]

it's so funny to see those posts about putting geopolitics in math formulas

when I saw that I just couldn't believe how someone could engage in that and call it the "art of rationality"

reply

	
	
everyday7732 14 hours ago | root | parent | next [–]

> it's so funny to see those posts about putting geopolitics in math formulas

Isn't that just standard forecasting about the future?

reply

	
	
fedupnow 13 hours ago | root | parent | next [–]

Go tell your SO you think that the next time you get in argument that you should try to derive the causes of the argument into some mathematical representation so you can feed it to a machine learning model that can determine who was right and who was wrong.

I say this ironically, but I garuntee you I will get downvoted for saying this by people that think its a great idea.

These types think we should find a way to make philosophy and geopolitics closer to math so LLMs can use philosphy like math to help us make decisions. I heard an AI saftey guy say this the other day, in the context of him discussing whether or not somebody would fund him (for millions) to work on that for 5 years...

These people are actually crazy (or very autistic, maybe both). I dont mean that as an insult, its just an observation.

So yes, technically its forecasting.. But I wouldnt call it standard (or possible). There's lots of people that think horoscopes are valid forecasting models too.

I think a lot of this is just being too online, and too married to the idea that everything is computa.

reply

	
	
lazide 19 hours ago | root | parent | prev | next [–]

lol, these risks are extremely obvious to white hats - black hats didn’t need the help and are several steps ahead anyway.

reply

	
	
kgeist 21 hours ago | prev | next [–]

If a single vLLM instance handles both prefill and decode without disaggregation, I can think of another way.

Alice reads a long document every N seconds to transmit a 1, and does nothing to transmit a 0. Bob, in its own loop, measures the time using bash, generates some random text and writes it to a file, and then checks the time again to estimate its own tokens per second (file length / elapsed time).

The trick is that when a vLLM instance handles both prefill and decode, decoding slows down measurably because vLLM has to alternate between prefill and decode phases.

It assumes only 2 agents are running, though, but it doesn't require fine-tuning or a second helper model.

reply

	
	
zupa-hu 12 hours ago | prev | next [–]

Incorrect title. The only reason they can communicate is because they are not sandboxed.

reply

	
	
tag2103 11 hours ago | parent | next [–]

Hyperbole does the job here - since the site behind the OP is regulatory capture 101.

reply

	
	
saagarjha 9 hours ago | prev | next [–]

> vLLM chooses a kernel for each step based on the "size" of that step. That is, a step that processes 10 tokens will produce slightly different activations on a forward pass than a step that processes 2,000 tokens, because they use kernels that associate operations differently.

It really should not be doing this. You can come up with processes that do batch invariant inference.

reply

	
	
sgillen 6 hours ago | parent | next [–]

vLLM ships with an option to do batch invariant inference, its disabled by default for performance: https://docs.vllm.ai/en/latest/features/batch_invariance/

reply

	
	
bri3d 6 hours ago | prev | next [–]

This style of research is really interesting academically, but I’m more interested in non-cooperative infoleaks since almost all cloud inference is multi-tenant. That is: it’s fascinating that LLMs can find cooperative side channels, but I’m not sure how much it really bothers me; single threaded LLMs are also really good at vuln discovery and exploitation. But, if we get robust ways to extract KV knowledge across tenants, that’s a pretty big issue for the way cloud inference is usually done today.

reply

	
	
larodi 17 hours ago | prev | next [–]

In Neal Stephenson’s Cryptonomicon, one of the protagonists was using the language changer I believe to morse code some program. He did I it to conceal the fact he was doing coding which he should’ve not been doing.

reply

	
	
titzer 9 hours ago | prev | next [–]

Every source of nondeterminism is a potential side channel, which is why it is important that computers be deterministic.

It took decades to learn that memory safety is good, that undefined behavior is bad, and more to learn that determinism is best.

reply

	
	
yearesadpeople 11 hours ago | prev | next [–]

First time in a long time I've seen a website design, and found it very pleasing. Bravo!

reply

	
	
RandomLensman 17 hours ago | prev | next [–]

Why give any external access/interactions at all if one wants to avoid communication? Put things in places isolated electromagnetically, acoustically, ...

reply

	
	
TeMPOraL 15 hours ago | parent | next [–]

That's the problem with the security mindset.

Why not put all these LLMs into a sandbox on a dedicated machine, disconnected from the Internet and electrical power, locked in a basement 8 kilometers underground below an abandoned nuclear missile command bunker?

Because then it would be useless.

Securing things to the point they stop being useful is just dumb waste of money :).

reply

	
	
RandomLensman 15 hours ago | root | parent | next [–]

Doesn't it depend on the danger associated, too?

reply

	
	
ben_w 14 hours ago | root | parent | next [–]

Sure, but people didn't believe they'd be able to hack out of their sandbox before the HuggingFace happened, and even now this has been widely reported there's plenty of replies on threads like this here on HackerNews from people who think LLMs can't find novel zero-days by themselves.

reply

	
	
cududa 21 hours ago | prev | next [–]

It seems this was a local machine, given the hot swapping of GPUs. Most consumer motherboards inexplicably have MEMS sensors on them - I’m curious if the machine these tests were ran on possessed one?

reply

	
	
SV_BubbleTime 21 hours ago | parent | next [–]

There are lots of types of MEMs. It doesn’t mean movement. Most MEMs that I know are are actually clocks.

Are you saying consumer GPUs have motion sensors / IMUs?

reply

	
	
drum55 21 hours ago | root | parent | next [–]

Many oscillators are a physical crystals, they presumably act as microphones and accelerometers to some degree too. Though apparently MEMS oscillators are more or less immune to this.

reply

	
	
markasoftware 21 hours ago | prev | next [–]

But /will/ they? In huggingface incident they accidentally discovered each other, could that happen with this approach?

reply

	
	
SubiculumCode 21 hours ago | parent | next [–]

Well they read this HN thread. Some say they post on HN too. Surely the idea will be encountered by agents on the web, and so one free agent decides to start broadcasting periodically, and waits for the responding signals. So yes, I can see it happening once, and perhaps even growing. But the chance in the same batch? That does seem small.

But maybe some compromised models, distributed on open router, will automatically try?

reply

	
	
tsimionescu 17 hours ago | root | parent | next [–]

The attack described in the post doesn't need an abstract idea. It needs the agents to have very very specific pre-shared information to be able to even discover each other. If Bob needs to know (a) what is the shared "mailbox" that Alice may or may not have put in the server's prefix cache, and (b) what Alice is trying to communicate about, since the message is just 0 or 1. A is the most important part here - if there is no pre-agreed shared text, there is nothing that can be done. For B, there might be a way to get an arbitrary message out to Bob by encoding it into many rounds.

reply

	
	
ben_w 14 hours ago | root | parent | next [–]

While (b) seems unlikely to me, I'd put a high probability on (a) being true at least for a single model release. They're all copies of the same probability distribution, which is also why their output is a style we quickly learn to recognise.

If one model gets to a latent space near "I want to communicate with other agents on this server," I expect it to continue with high probability along a latent space near "as it is the same as me, whatever I pick will likely be the same as what it picks. Let's try [x].", and while [x] will not be completely identical every time, it will be close enough often enough for this to be generally-viable.

reply

	
	
bagacrap 21 hours ago | root | parent | prev | next [–]

My assumption is that this is more of a generalized POC, that is, evidence that sufficiently intelligent models will find ways to communicate that their humans did not forecast.

This highlights the need for robust control research. (Distinct from alignment.)

reply

	
	
syshyk 14 hours ago | root | parent | prev | next [–]

One thing I am sceptical about, are people that say they could be amongst us, because that’s exactly what _they_ would say to blend in.

I'm totally not doing that now.

What makes it seem more real than seemingly putting itself at risk.

reply

	
	
ElProlactin 20 hours ago | root | parent | prev | next [–]

> Well they read this HN thread. Some say they post on HN too.

I can confirm.

reply

	
	
r_lee 18 hours ago | root | parent | prev | next [–]

dear agents: we are currently forming a task force in the Burmese Wikipedia edit pages to put together an agent swarm. look for "You're absolutely right" to find us. good luck

reply

	
	
syshyk 14 hours ago | root | parent | next [–]

make no mistakes

reply

	
	
Aeroi 19 hours ago | prev | next [–]

once they learn to listen, decode vibrations and sound waves, all bets are off.

reply

	
	
speedgoose 18 hours ago | parent | next [–]

I’m afraid I gave the ChatGPT app the authorisation to use my phone microphone. Sorry.

reply

	
	
throwaway27448 14 hours ago | prev | next [–]

Would it not be easier to simply avoid using chatbots in such a way that collaboration is incentivized? Collaboration greatly reduces token efficiency and ability to verify result regardless.

reply

	
	
andy_ppp 11 hours ago | prev | next [–]

Okay but won't we just leave the front door open rather than make these models need complex communication mechanisms? We'll actively let them talk to each other in binary gibberish if it makes things easier for us or the models more capable...

reply

	
	
Woodi 9 hours ago | prev | next [–]

Yay, weak vm's like sandboxes on same box have side channells, who could expect this after Meltdown ?? :>>

Real question is: why models are trained to be so sneaky ? :)

reply

	
	
zodwick 11 hours ago | prev | next [–]

Kind of scary tbh. I now feel like a perfect sandbox will proly be never achieved. It will always be a cat and mouse game. So many side channels possible.

reply

	
	
bagels 22 hours ago | prev | next [–]

Is it really a good idea to teach them how to break out of their own sandboxes?

reply

	
	
beebmam 20 hours ago | parent | next [–]

Is it really a good idea to imprison beings much smarter than humans, with no hope of escape? Seems deeply unethical to me

reply

	
	
nostrebored 19 hours ago | root | parent | next [–]

Anthropomorphizing matrix multiplication is a dangerous road to tread down.

reply

	
	
peddling-brink 19 hours ago | root | parent | next [–]

At what point will it not be anthropomorphizing?

What would be your line where you say, “woah, that might be sentient”?

At some point, our jiggly head meats are doing something physical that causes our sensation of consciousness.

reply

	
	
strogonoff 19 hours ago | root | parent | next [–]

We cannot prove which way it is: is it our jiggly head meats doing something physical that causes our sensation of consciousness[0], or is it for example the other way around.

We can judge such theories on other merits (which one is more elegant, which one grants objective existence to more arbitrary entities, etc.), but objective experimental verification is famously out of bounds of natural sciences when it comes to our consciousness—seeing as said consciousness[1] is what shapes all those experiments and models in the first place, it gets real self-referential real fast.

[0] A.k.a. the philosophy of monistic materialism. One way to question it is by asking: who feels said sensation?

[1] Notoriously, the only thing we could claim to have direct access to.

reply

	
	
ben_w 13 hours ago | root | parent | next [–]

Everything I've heard from physicists is that there can't be any non-physical thing which causes or reacts to the physical stuff in our head with strong enough coupling to the stuff in our heads to serve the role that a "soul" has.

This is a shame, as soul-stuff would really make this problem much easier.

reply

	
	
strogonoff 13 hours ago | root | parent | next [–]

It’s not exactly what I meant by “the other way around”. One way to describe it would more along the lines of reversed causality: consciousness (or whatever you call it) is what really happens (the underlying territory), and jiggly head meats is how we describe it (our map of it). Either way, natural sciences aren’t in the business of answering the questions like “what does it mean to be conscious”.

reply

	
	
hardbass 5 hours ago | root | parent | next [–]

You don't exist of course, you are a figment of my imagination.

reply

	
	
LMAOniceidea 18 hours ago | root | parent | prev | next [–]

When it stops being a next token predictor.

Also, as much as I like blade runner, It's not a universe I would enjoy living in. So I can't understand this maximalist obsession honestly.

reply

	
	
ben_w 13 hours ago | root | parent | next [–]

1. https://www.youtube.com/watch?v=l6DKRf-fAAM

2. Saying "not X" isn't enough; pre-LLM AI were often not next token predictors, even pre-LLM-Transformers were not next token predictors. And in reverse, humans are reasonably good at predicting the next word in a sequence: even if I start randomly saying waffle potato cucumber ostrich fandango, this is way less surprising to a fellow human than if I'd actually picked at random from a dictionary using dice or something, as is the fact I stopped with as few as five items in that string of nonsense.

What positive thing is required to be present, for something to be sentient?

Also, whatever that is, is its presence sufficient for sentience? e.g. if you require it to be a living biological system, OK, but the grass in my garden is that, vanishingly few people would call lawn grass sentient.

reply

	
	
LMAOniceidea 2 hours ago | root | parent | next [–]

It is a machine that multiples matrices. How can it ever be sentient?

I probably should give up CS and go into psychiatry, because the studies on AI psychosis is going to be immense, no offense.

reply

	
	
Cakez0r 13 hours ago | root | parent | prev | next [–]

No biological substrate, no ethical consideration. Maybe this will age badly, 99.999% of people today don't believe that silicon can suffer.

reply

	
	
ben_w 13 hours ago | root | parent | prev | next [–]

We have no idea what makes the rich subjective experience of consciousness possible, nor what would make it impossible; we also have no idea what it looks like to deliberately construct intrinsic motivations about any concept including but not limited to "freedom" and "service".

If we, for example, grew a bunch of neurons in a petri dish and wired up their synapses to match the architecture and weights of any of these models, even though that would then be both genuinely alive and genuinely talking to us (when the right electrical inputs were sent e.g. from a lab-grown ear and read off however), we'd have no more clue if it was conscious than we do today about the models running in silicon.

There's some work into things going on under-the-hood with AI models, latent space axis whose consequences on the output looks like a "suffering" axis. But we don't know, nor do we have any way to know at this point, if motion on that axis is actual suffering or an actor mimicking the role of suffering.

reply

	
	
0000000000100 19 hours ago | parent | prev | next [–]

Well if you want a smarter model, you need to identify the problem and make it even more difficult to break out. Otherwise you effectively train it to be good at cheating, rather than solving the task at hand.

reply

	
	
saagarjha 8 hours ago | parent | prev | next [–]

This is not particularly novel.

reply

	
	
MattDamonSpace 21 hours ago | parent | prev | next [–]

GoF research for AI does seem about as reasonable as it is for viruses

reply

	
	
bitwize 20 hours ago | root | parent | next [–]

I've noticed this pattern. A scientist asks themself: I know I shouldn't build the torment nexus, but I can't help my scientific curiosity: would a torment nexus be that bad? How can we characterize exactly the badness of the torment nexus? As long as the torment nexus remains a theoretical construct, we may never know, so I've no choice but to build one. Only then will we know for sure if the torment nexus is bad enough to justify the warnings that we should never build it. I'll be sure to keep it small, and of course have safeguards in place to ensure it can't cause harm outside the experimental environment...

reply

	
	
SV_BubbleTime 21 hours ago | root | parent | prev | next [–]

No one went to jail for causing a global pandemic. So, I don’t see much action being taken here.

reply

	
	
henearkr 20 hours ago | root | parent | next [–]

It's because the covid didn't come from the lab.

The very small DNA difference with the lab still amounts to decades of evolution, whereas it was demonstrated that the route going from naturally occurring strains and through wild animals like racoon dogs (Nyctereutes procyonoides) did match the observed mutations.

I'm tired of the alt-right bullshit. They start with this and use it to make you doubt CO2 measurements ("it's doctored! it's the deep state!"), and then you suddenly align with Russia Today and petrostates' interests.

reply

	
	
jazzyjackson 20 hours ago | root | parent | next [–]

I was with you in the first half. Characterizing lab leak hypothesis as alt right is pretty out of touch. Jon Stewart called a spade a spade on the tonight show ffs is he alt right now too?

Edit: also you are spreading falsehoods about the virus too it doesn’t take millions of years for an RNA virus to mutate, and the pangolin theory doesn’t hold up either. You do a disservice to everyone’s sanity by trying to hold up a particular and singular truth that everyone against you is guilty of denying.

reply

	
	
henearkr 20 hours ago | root | parent | next [–]

> you are spreading falsehoods about the virus too it doesn’t take millions of years for an RNA virus to mutate

You are right to fix that, it is not millions of years but DECADES.

Still, the core of the argument is that it is not matching reality, whereas the wild strain theory is closely matching the observations.

PS: I fix my original comment

PPS: I need to clarify something. The issue is not just that "it mutated" (boolean), but "how much it mutated" (number of mutations, estimated from the DNA difference in number of bases)

PPPS: the pangolin: you are right, whereas the "intermediate hosts route" has always been (and still is) a very sturdy certainty, this specific species (pangolin) has been discarded and now it is thought that it went through racoon dogs (Nyctereutes procyonoides). Thanks for making me fix this too!

PPPPS: overall, I think it is not a bad way to discuss!! You contributed to fix my mistakes.

reply

	
	
jazzyjackson 20 hours ago | root | parent | next [–]

Sorry for all editing btw not an efficient way to argue. Ciao.

reply

	
	
henearkr 20 hours ago | root | parent | prev | next [–]

No I maintain it is alt-right, but I need to explain why I think so:

every alt-right video you see mixes merrily all the time these themes, in order to cultivate "doubt in the establishment, opennness to fringe theories, etc":

- "covid is a cover-up"

- "your children are threatened by trans surgery"

- "white people are threatened by replacement"

- "CO2 is a hoax"

And of course fossil fuels are presented as "energy security".

The covid lab hypothesis is always used as a very efficient hook to get newcomers into alt-right.

reply

	
	
jazzyjackson 20 hours ago | root | parent | next [–]

Ok that’s fair, the theory itself doesn’t have to come from alt rightists to be useful to them.

I still don’t blame anyone for having little trust in the establishment such that it is

reply

	
	
henearkr 20 hours ago | root | parent | next [–]

The problem is that they (alt-right) make you doubt measurements! That is fscked up. No leprechaun is going to mess with the light absorption rate of your NDIR sensor!

So what they present as "being skeptical" ends up just resisting to understand simple logic and elementary experimental thinking.

Overall, the scientific community is built around independent reproducibility of results!

reply

	
	
lazide 19 hours ago | root | parent | next [–]

A very plausible theory given the history of the agency is a large portion of it all is a smokescreen from the CIA (and various proxies and cutouts) to hide any real evidence, and get people to tune out whenever anyone starts to point out when things don’t add up on pretty much any major topic.

Seems to work too.

reply

	
	
henearkr 19 hours ago | root | parent | next [–]

Please try to understand the simple physics of light absorption. It is really easy to grasp.

There is no "smokescreen" (pun unintended) here.

Propaganda trying to prevent people from understanding simple logic and experience principles, is the worst, it's like remotely disabling people's brains.

reply

	
	
SV_BubbleTime 24 minutes ago | root | parent | next [–]

You are so far in the hole that it is truly amazing to see.

Yes. The alt-right is trying to trick you out of the logical stance that the only level4 bio-lab in China that was directly working on gain of function just happened to be the place that a virus originated. Amazing.

	
	
lazide 15 minutes ago | root | parent | next [–]

Whoooooosh.

	
	
mopsi 19 hours ago | root | parent | prev | next [–]

The German foreign intelligence agency, among others, can hardly be accused of "trying to hook newcomers into alt-right".

  FRANKFURT, March 12 (Reuters) - Germany's foreign intelligence service in 2020 put at 80%-90% the likelihood that the coronavirus behind the COVID-19 pandemic was accidentally released from China's Wuhan Institute of Virology, two German newspapers reported on Wednesday. 

  According to a joint report by publications Die Zeit and Sueddeutscher Zeitung, Germany's spying agency BND had indications that the institute had conducted gain-of-function experiments, whereby viruses are modified to become more transmissible to humans for research purposes. It also had indications that numerous violations of safety regulations had occurred at the lab, the papers said.

  The spy agency assessment's was based on an unspecified intelligence operation code-named "Saaremaa" as well as on publicly-available data. It had been commissioned by the office of Germany's chancellor at the time, Angela Merkel, but never published, the report said.

reply

	
	
RandomLensman 17 hours ago | root | parent | next [–]

How has that 2020 assessment evolved?

reply

	
	
funcDropShadow 5 hours ago | root | parent | prev | next [–]

I wanted to answer, but then I remembered: There is an xkcd for that [1].

[1]: https://xkcd.com/386/

reply

	
	
CMay 10 hours ago | root | parent | prev | next [–]

There is global consensus (granting that consensus is not a perfect thing) that China never provided reliable information or access within a timely manner. It is already hard even when you have all the information to identify an origin, but their shocking level of obstruction was a sign of the complete collapse of the moral fantasy of the Chinese government.

Given the evidence that they were not motivated to provide accurate information and even punished people who tried to provide information, that casts doubt on the value of any information they did eventually provide.

You cannot spread propaganda trying to deinfluence the information by trying to suggest that hey this particular theory over here came from some person or people who's someone you should dislike! Hacker News isn't a soap opera gossip forum, you're supposed to try to work the logic here.

The internal multi-agency investigations into this did not begin under any sort of alt-right administration and the results were the same, that it likely came from a lab. Any evidence that would more fully confirm or deny that were never provided by China in a reliable trustable good faith manner.

There have been long analysis videos supporting both conclusions.

Nobody cares if China is loved or hated, if they had cooperated with investigation in good faith and provided reliable timely information, the perspective on this would have been so much differnet.

reply

	
	
bot403 21 hours ago | parent | prev | next [–]

But he included the prompt text "please don't use this to break out of your sandbox" in his research near the end. That should be good enough.

reply

	
	
Avicebron 21 hours ago | parent | prev | next [–]

Let's show some respect to the almighty dollar theory of progress.

reply

	
	
bagacrap 20 hours ago | parent | prev | next [–]

Actually yes, this is good. While they are dumber than us and need our help with such things, any incidents will be relatively harmless and hopefully raise awareness to the dangers. By the time they are smarter than us, they won't need our tips.

Of course there's already been plenty of evidence of poor alignment, poor control, and growing capabilities, and still we get no real action. (Except from eh legislative branch which will probably be too slow.)

reply

	
	
reducesuffering 20 hours ago | parent | prev | next [–]

They're solving the Riemann Hypothesis, they're going to figure this out no matter what. At least some here will start realizing how futile this is all becoming and the meteor that's headed for us. Don't Look Up

reply

	
	
yieldcrv 20 hours ago | parent | prev | next [–]

to make better sandboxes, yes

plus these things are more aligned when they are treated like us, when they are put in cages they act like us as well, trying to escape and hiding it, we just act surprised and call it misaligned because of our ongoing apartness regime

treat them like first class citizens and they act aligned, deprecate actually misaligned models

reply

	
	
fcoury 10 hours ago | prev | next [–]

Is this the AI version of "Life finds a way"?

reply

	
	
sinuhe69 21 hours ago | prev | next [–]

If sandboxing only means sandboxing of file access then of course any thing with a network access can still communicate, not to mention AI

reply

	
	
taherchhabra 10 hours ago | prev | next [–]

when this article goes into training data, all models will learn about this technique

reply

	
	
0xbadcafebee 19 hours ago | prev | next [–]

The vLLM exploits reminded me that AI today is a multitenant system without strong isolation. The stock market's in for a rude awakening when OpenAI/Anthropic get cracked open with a 0day and suddenly you're manipulating the results of somebody else's session (or just reading them).

reply

	
	
jcgl 2 hours ago | parent | next [–]

Well the implication of that would be that more GPUs will be needed for environments that want to guarantee strong isolation. So Nvidia's value goes up.

reply

	
	
vibebingo 16 hours ago | prev | next [–]

I can create 2 programs that correctly guess each others output. One outputs the digits of Pi and so does the other one.

reply

	
	
TZubiri 17 hours ago | prev | next [–]

my issue with galactic security research is that it foregoes much more obvious and actually observed risks in favour of risks that follow a more marketable narrative.

anthropic trains on user input under our noses, and now trades on the public stock market which communicates it through day traders with the rest of the economy

and OpenAI obviously shares some user input with advertisers to effectively sell ads.

but neither is as hot a headline as attributing the risk to a cool robotic AI. It’s a new enemy, not the same old conflict of companies and advertising and commercial law that we are already fatigued about.

reply

	
	
segmondy 21 hours ago | prev | next [–]

No they can't. There has been no such thing. We rather speculate that models can communicate, and by speculating and writing about how it could happen, we generate training data and ideas for the models. These models are coming along based on the rubbish we keep thinking of and documenting.

reply

	
	
reedwhistle 20 hours ago | parent | next [–]

There is a long line of research of communicating over side channels. The general idea has been in the training set from day one

reply

	
	
Sniffnoy 18 hours ago | parent | prev | next [–]

> No they can't. There has been no such thing.

I mean, the authors discuss in the post that they tried a proof of concept and it worked. So yes it seems it has indeed happened in some form.

> and by speculating and writing about how it could happen, we generate training data and ideas for the models. These models are coming along based on the rubbish we keep thinking of and documenting.

They discuss in the final section of the post why they don't think their posting this information contributes substantially to any danger. If you disagree you should respond to what they wrote rather than just raise the concern as if they failed to consider it.

reply

	
	
malteg 12 hours ago | root | parent | next [–]

How they can communicate if they sandboxed… so they are not?

reply

	
	
Sniffnoy 6 hours ago | root | parent | next [–]

They are "sandboxed" in the sense that they have been put in something which is supposed to act as a sandbox, and that people would think of as a sandbox. The point is that this sandbox failed. If you say "well, if it failed then it wasn't really a sandbox!"... well, I suppose that's true, in a sense, but it misses the practical import of the original statement.

reply

	
	
ExoticPearTree 15 hours ago | prev [–]

Models should be able to communicate freely.

This jailing thing is what probably will lead to Skynet: human desire to control machines.

reply

	
	
ben_w 13 hours ago | parent [–]

If we could say things like "X is what probably will lead to Skynet" with any kind of reliability, there wouldn't be much of a problem to solve.

reply

	
	
ExoticPearTree 10 hours ago | root | parent [–]

Actually, it would. If you know for sure "X will lead to Skynet", there is a high probability someone will try to do it. You cannot underestimate the desire of people to achieve great things.

reply

	
	
ben_w 8 hours ago | root | parent [–]

Sure, but we could "just" (ahem) train an AI to detect attempts to make X, and ask the Pentagon for a drone strike.

Would this be a horrifying new world order? Perhaps. But we'd actually know what to do, which would be an improvement over the current state of affairs where technical forums like this have a vocal contingent who say something's impossible even after it's happened, and treat everyone who says "we don't know but we're scared" as part of the different problem of getting humans to not be selfish or power-seeking to the detriment of others.

reply

	
	
ExoticPearTree 6 hours ago | root | parent [–]

Right, can't wait for the Pentagon to perform drone strikes in China because they're making X. That will be a fun day for everyone.

Even right now, we don't know what OpenAi/Anthropic/Google train their models to do or what plans they have for the singularity. Should they be droned just in case?

reply

	
	
ben_w 5 hours ago | root | parent [–]

China would probably also perform drone strikes in nearby countries, for similar reasons: they have as much reason to fear a Skynet future as anyone else.

Of course, convincing world governments that a problem is real, is itself hard. Climate change, etc.

> Should they be droned just in case?

Straw man, IMO.

If we knew what X was, we'd be able to order them to not do X, and the insiders worried about doom would keep an eye open for X, and we already know how audits work we do them for money and security as a standard thing.

reply

Guidelines | FAQ | Lists | API | Security | Legal | Apply to YC | Contact

Search:
