Introduction: Mind over Data
The introduction describes the inadequacy of early 20th century statistical methods at making statements about causal relationships between variables. The authors then describe what they term 'The Causal Revolution', which started in the middle of the 20th century, and provided new conceptual and mathematical tools for describing causal relationships.

Chapter 1: The Ladder of Causation
Chapter 1 introduces the 'ladder of causation' - a diagram used to illustrate the three levels of causal reasoning. The first level is named 'Association', which discusses associations between variables. Questions such as 'is variable X associated with variable Y?' can be answered at this level. However, crucially, causality is not invoked. An example of reasoning on this first level is the observation that a crowing rooster is associated with the sunrise. However, this kind of reasoning cannot describe causal relations. For example, we cannot say whether the sunrise causes the rooster to crow, or whether the rooster causes the sun to rise. Many of the early 20th century statistical tools, such as correlation and regression operate on this level.

The second level (or 'rung') on the ladder of causation is labelled 'Intervention'. Reasoning on this level answers questions of the form 'if I make the intervention X, how will this affect the probability of the outcome Y?'. For example, the question 'does smoking increase my chance of lung cancer?' exists on the second level of the ladder of causation. This kind of reasoning invokes causality and can be used to investigate more questions than the reasoning of the first rung.

The third rung of the ladder of causation is labelled 'Counterfactuals' and involves answering questions which ask what might have been, had circumstances been different. Such reasoning invokes causality to a greater degree than the previous level. An example counterfactual question given in the book is 'Would Kennedy be alive if Oswald had not killed him?'

Chapter 2: From Buccaneers to Guinea Pigs: The Genesis of Causal Inference
Chapter 2 starts with a brief summary of the contributions of Francis Galton and Karl Pearson (originally Carl Pearson) to the development of statistics in the late 19th Century and early 20th Centuries. The authors blame Karl Pearson for keeping the study of statistics on the first rung of the ladder of causation and discouraging any discussion of causality in statistics. Causal analysis using path diagrams is then introduced through the explanations of the work of Sewall Wright.

Chapter 3: From Evidence to Causes: Reverend Bayes meets Mr Holmes
Chapter 3 provides an introduction to Bayes' Theorem. Then Bayesian Networks are introduced. Finally, the links between Bayesian networks and causal diagrams are discussed.

Chapter 4: Confounding and Deconfounding, or, Slaying the Lurking Variable
This chapter introduces the idea of confounding and describes how causal diagrams can be used to identify confounding variables and determine their effect. Pearl explains that randomized controlled trials (RCTs) can be used to nullify the effect of confounders, but shows that, provided one has a causal model of confounding, an RCT does not necessarily have to be performed to get results.

Chapter 5: The Smoke-filled Debate: Clearing the Air
This chapter takes a historical approach to the question 'does smoking cause lung cancer?', focusing on the arguments made by Abraham Lilienfeld, Jacob Yerushalmy, Ronald Fisher and Jerome Cornfield. The authors explain that, though cigarette smoking was clearly correlated with lung cancer, some, such as Fisher and Yerushalmy, believed that the two variables were confounded and argued against the hypothesis that cigarettes caused the cancer. The authors then explain how causal reasoning (as developed in the rest of the book) can be used to argue that cigarettes do indeed cause cancer.

Chapter 6: Paradoxes Galore!
This chapter examines several paradoxes, including the Monty Hall Problem, Simpson's paradox, Berkson's paradox and Lord's paradox. The authors show how these paradoxes can be resolved using causal reasoning.

Chapter 7: Beyond Adjustment: The Conquest of Mount Intervention
This chapter looks at the 'second rung' of the ladder of causation introduced in chapter 1. The authors describe how to use causal diagrams to ascertain the causal effect of performing interventions (eg. smoking) on outcomes (such as lung cancer). The 'front-door criterion' and the 'do-calculus' are introduced as tools for doing this. The chapter finishes with two examples, used to introduce the use of instrumental variables to estimate causal relationships. The first is John Snow's discovery that cholera is caused by unsanitary water supplies. The second is the relationship between cholesterol levels and likelihood of a heart attack.

Chapter 8: Counterfactuals: Mining worlds that could have been
This chapter examines the third rung of the ladder of causation: counterfactuals. The chapter introduces 'structural causal models', which allow reasoning about counterfactuals in a way that traditional (non-causal) statistics does not. Then, the applications of counterfactual reasoning are explored in the areas of climate science and the law.

Chapter 9: Mediation: The Search for Mechanism
This chapter discusses mediation: the mechanism by which a cause leads to an effect. The authors discuss the work of Barbara Stoddard Burks on the causes of intelligence of children, the 'algebra for all' policy by Chicago public schools, and the use of tourniquets to treat combat wounds.

Chapter 10: Big Data, Artificial Intelligence and the Big Questions
The final chapter discusses the use of causal reasoning in big data and artificial intelligence (AI) and the philosophical problem that AI would have to reflect on its own actions, which requires counterfactual (and therefore causal) reasoning.

Reviews

BOOK REVIEW
The Book of Why
A review by Lisa R. Goldberg
The Book of Why
The New Science of Cause and Effect
Judea Pearl and Dana Mackenzie
Basic Books, 2018
432 pages
ISBN-13: 978-0465097609
Judea Pearl is on a mission to
change the way we interpret
data. An eminent professor
of computer science, Pearl has
documented his research and opinions in scholarly books
and papers. Now, he has made his ideas accessible to
a broad audience in The Book of Why: The New Science
of Cause and Effect, co-authored with science writer Dana
Mackenzie. With the release of this historically grounded
and thought-provoking book, Pearl leaps from the ivory
tower into the real world.
The Book of Why takes aim at perceived limitations of
observational studies, whose underlying data are found in
nature and not controlled by researchers. Many believe
that an observational study can elucidate association but
not cause and effect. It cannot tell you why.
Perhaps the most famous example concerns the impact
of smoking on health. By the mid 1950s, researchers had
established a strong association between smoking and
lung cancer. Only in 1984, however, did the US government mandate the phrase “smoking causes lung cancer.”
Lisa Goldberg is a co-director of the Consortium for Data Analytics in Risk and
an adjunct professor of Economics and Statistics at University of California,
Berkeley. She is a director of research at Aperio Group, LLC. Her email address
is lrg@berkeley.edu.
Communicated by Notices Book Review Editor Stephan Ramon Garcia.
For permission to reprint this article, please contact:
reprint-permission@ams.org.
DOI: https://doi.org/10.1090/noti1912
The holdup was the specter of a latent factor, perhaps something genetic, that might cause both lung cancer and a craving for tobacco. If the latent factor were responsible for
lung cancer, limiting cigarette smoking would not prevent
the disease. Naturally, tobacco companies were fond of
this explanation, but it was also advocated by the prominent statistician Ronald A. Fisher, co-inventor of the socalled gold standard of experimentation, the Randomized
Controlled Trial (RCT).
Subjects in an RCT on smoking and lung cancer would
have been assigned to smoke or not on the flip of a coin.
The study had the potential to disqualify a latent factor
as the primary cause of lung cancer and elevate cigarettes
to the leading suspect. Since a smoking RCT would have
been unethical, however, researchers made do with observational studies showing association, and demurred on
the question of cause and effect for decades.
Was the problem simply that the tools available in the
1950s and 1960s were too limited in scope? Pearl addresses that question in his three-step Ladder of Causation,
which organizes inferential methods in terms of the problems they can solve. The bottom rung is for model-free
statistical methods that rely strictly on association or correlation. The middle rung is for interventions that allow
for the measurement of cause and effect. The top rung is
for counterfactual analysis, the exploration of alternative
realities.
Early scientific inquiries about the relationship between
smoking and lung cancer relied on the bottom rung,
model-free statistical methods whose modern analogs
dominate the analysis of observational studies today. In
one of The Book of Why’s many wonderful historical anecdotes, the predominance of these methods is traced to the
work of Francis Galton, who discovered the principle of regression to the mean in an attempt to understand the process that drives heredity of human characteristics. Regression to the mean involves association, and this led Galton
AUGUST 2019 NOTICES OF THE AMERICAN MATHEMATICAL SOCIETY 1093Book Review
and his disciple, Karl Pearson, to conclude that association
was more central to science than causation.
Pearl places deep learning and other modern data mining tools on the bottom rung of the Ladder of Causation.
Bottom rung methods include AlphaGo, the deep learning
program that defeated the world’s best human Go players
in 2015 and 2016 [1]. For the benefit of those who remember the ancient times before data mining changed everything, he explains,
The successes of deep learning have been truly remarkable and have caught many of us by surprise.
Nevertheless, deep learning has succeeded primarily by showing that certain questions or tasks we
thought were difficult are in fact not.
The issue is that algorithms, unlike three-year-olds, do as
they are told, but in order to create an algorithm capable
of causal reasoning,
...we have to teach the computer how to selectively
break the rules of logic. Computers are not good
at breaking rules, a skill at which children excel.
Figure 1. Causal model of assumed relationships among
smoking, lung cancer, and a smoking gene.
Methods for extracting causal conclusions from observational studies are on the middle rung of Pearl’s Ladder of
Causation, and they can be expressed in a mathematical
language that extends classical statistics and emphasizes
graphical models.
Various options exist for causal models: causal diagrams, structural equations, logical statements,
and so forth. I am strongly sold on causal diagrams for nearly all applications, primarily due to
their transparency but also due to the explicit answers they provide to many of the questions we
wish to ask.
The use of graphical models to determine cause and effect
in observational studies was pioneered by Sewall Wright,
whose work on the effects of birth weight, litter size, length
of gestation period, and other variables on the weight of a
33-day-old guinea pig is in [2]. Pearl relates Wright’s persistence in response to the cold reception his work received
from the scientific community.
My admiration for Wright’s precision is second
only to my admiration for his courage and determination. Imagine the situation in 1921. A selftaught mathematician faces the hegemony of the
statistical establishment alone. They tell him
“Your method is based on a complete misapprehension of the nature of causality in the scientific
sense.” And he retorts, “Not so! My method is
important and goes beyond anything you can generate.”
Pearl defines a causal model to be a directed acyclic graph
that can be paired with data to produce quantitative causal
estimates. The graph embodies the structural relationships
that a researcher assumes are driving empirical results. The
structure of the graphical model, including the identification of vertices as mediators, confounders, or colliders,
can guide experimental design through the identification
of minimal sets of control variables. Modern expositions
on graphical cause and effect models are [3] and [4].
Figure 2. Mutated causal model facilitating the calculation of
the effect of smoking on lung cancer. The arrow from the
confounding smoking gene to the act of smoking is deleted.
Within this framework, Pearl defines the do operator,
which isolates the impact of a single variable from other
effects. The probability of 𝑌 do 𝑋, 𝑃[𝑌|do(𝑋)], is not
the same thing as the conditional probability of 𝑌 given
𝑋. Rather 𝑃[𝑌|do(𝑋)] is estimated in a mutated causal
model, from which arrows pointing into the assumed
cause are removed. Confounding is the difference between
𝑃[𝑌|do(𝑋)] and 𝑃[𝑌|𝑋]. In the 1950s, researchers were
after the former but could estimate only the latter in observational studies. That was Ronald A. Fisher’s point.
Figure 1 depicts a simplified relationship between smoking and lung cancer. Directed edges represent assumed
causal relationships, and the smoking gene is represented
by an empty circle, indicating that the variable was not observable when the connection between smoking and cancer was in question. Filled circles represent quantities that
could be measured, like rates of smoking and lung cancer
in a population. Figure 2 shows the mutated causal model
that isolates the impact of smoking on lung cancer.
The conclusion that smoking causes lung cancer was
eventually reached without appealing to a causal model. A
crush of evidence, including the powerful sensitivity anal-
1094 NOTICES OF THE AMERICAN MATHEMATICAL SOCIETY VOLUME 66, NUMBER 7Book Review
ysis developed in [5], ultimately swayed opinion. Pearl argues that his methods, had they been available, might have
resolved the issue sooner. Pearl illustrates his point in a
hypothetical setting where smoking causes cancer only by
depositing tar in lungs. The corresponding causal diagram
is shown in Figure 3. His front door formula corrects for the
confounding of the unobservable smoking gene without
ever mentioning it. The bias-corrected impact of smoking,
𝑋, on lung cancer, 𝑌, can be expressed
𝑃[𝑌|do(𝑋)] = ∑
𝑍
𝑃[𝑍|𝑋] ∑
𝑋′
𝑃[𝑌|𝑋′, 𝑍]𝑃[𝑋′].
Figure 3. Pearl’s front door formula corrects for bias due to
latent variables in certain examples.
The Book of Why draws from a substantial body of academic literature, which I explored in order to get a more
complete picture of Pearl’s work. From a mathematical
perspective, an important application is Nicholas Christakis and James Fowler’s 2007 study described in [6] arguing that obesity is contagious. The attention-grabbing
claim was controversial because the mechanism of social
contagion is hard to pin down, and because the study was
observational. In their paper, Christakis and Fowler upgraded an observed association, clusters of obese individuals in a social network, to the assertion that obese individuals cause their friends, and friends of their friends, to
become obese. It is difficult to comprehend the complex
web of assumptions, arguments, and data that comprise
this study. It is also difficult to comprehend its nuanced
refutations by Russell Lyons [7] and by Cosma Shalizi and
Andrew Thomas [8], which appeared in 2011. There is a
moment of clarity, however, in the commentary by Shalizi and Thomas, when they cite Pearl’s theorem about nonidentifiability in particular graphical models. Using Pearl’s
results, Shalizi and Thomas show that in the social network that Christakis and Fowler studied, it is impossible
to disentangle contagion, the propagation of obesity via
friendship, from the shared inclinations that led the friendship to be formed in the first place.
The top rung of the Ladder of Causation concerns counterfactuals, which Michael Lewis brought to the attention
of the world with his best selling book, The Undoing Project
[9]. Lewis tells the story of Israeli psychologists Daniel
Kahneman and Amos Tversky, experts in human error, who
fundamentally changed our understanding of how we
make decisons. Pearl draws on the work of Kahneman and
Tversky in The Book of Why, and Pearl’s approach to analyzing counterfactuals might be best explained in terms of a
question that Kahneman and Tversky posed in their study
[10] of how we explore alternative realities.
How close did Hitler’s scientists come to developing the atom bomb in World War II? If they had
developed it in February 1945, would the outcome
of the war have been different?
—The Simulation Heuristic
Pearl’s response to this question includes the probability of
necessity for Germany and its allies to have won World II
had they developed the atom bomb in 1945, given our historical knowledge that they did not have an atomic bomb
in February 1945 and lost the war. If 𝑌 denotes Germany
winning or losing the war (0 or 1) and 𝑋 denotes Germany
having the bomb in 1945 or not having it (0 or 1), the
probability of necessity can be expressed in the language
of potential outcomes,
𝑃 [𝑌𝑋=0 = 0 | 𝑋 = 1, 𝑌 = 1] .
Dual to the probability of sufficiency, the probability of necessity mirrors the legal notion of “but-for” causation as
in: but for its failure to build an atomic bomb by February
1945, Germany would probably have won the war. Pearl
applies the same type of reasoning to generate transparent
statements regarding climate change. Was anthropogenic
global warming responsible for the 2003 heat wave in Europe? We’ve all heard that while global warming due to human activity tends to raise the probability of extreme heat
waves, it is not possible to attribute any particular event
to this activity. According to Pearl and a team of climate
scientists, the response can be framed differently: There is
a 90% chance that the 2003 heat wave in Europe would
not have occurred in the absence of anthropogenic global
warming [11].
This formulation of the impact of anthropogenic global
warming on the earth is strong and clear, but is it correct?
The principle of garbage-in-garbage-out tells us that results
based on a causal model are no better than its underlying assumptions. These assumptions can represent a researcher’s knowledge and experience. However, many
scholars are concerned that model assumptions represent
researcher bias, or are simply unexamined. David Freedman emphasizes this in [12], and as he wrote more recently in [13],
Assumptions behind models are rarely articulated,
let alone defended. The problem is exacerbated because journals tend to favor a mild degree of novelty in statistical procedures. Modeling, the search
for significance, the preference for novelty, and the
lack of interest in assumptions—these norms are
AUGUST 2019 NOTICES OF THE AMERICAN MATHEMATICAL SOCIETY 1095Book Review
likely to generate a flood of non-reproducible results.
—Oasis or Mirage?
Causal models can be used to work backwards from
conclusions we favor to supporting assumptions. Our tendency to reason in the service of our prior beliefs is a favorite topic of moral psychologist Jonathan Haidt, author
of The Righteous Mind [14], who wrote about “the emotional dog and its rational tail.” Or as Udny Yule explained
in [15],
Now I suppose it is possible, given a little ingenuity and good will, to rationalize very nearly anything.
—1926 presidential address to the Royal
Statistical Society
Concern about the impact of biases and preconceptions
on empirical studies is growing, and it comes from sources
as diverse as Professor of Medicine John Ioannides, who
explained why most published research findings are false
[16]; comedian John Oliver, who warned us to be skeptical when we hear the phrase “studies show” [17]; and
former New Yorker writer Jonah Lehrer, who wrote about
the problems with empirical science in [18] but was later
discredited for representing stuff he made up as fact.
The graphical approach to causal inference that Pearl favors has been influential, but it is not the only approach.
Many researchers rely on the Neyman (or Neyman–Rubin)
potential outcomes model, which is discussed in [19], [20],
[21] and [22]. In the language of medical randomized control trials, a researcher using this model tries to quantify
the difference in impact between treatment and no treatment on subjects in an observational study. Propensity
scores are matched in an attempt to balance inequities between treated and untreated subjects. Since no subject can
be both treated and untreated, however, the required estimate of impact is sometimes formulated as a missing
value problem, a perspective that Pearl strongly contests.
In another direction, the concept of fixing, developed by
Heckman in [23] and Heckman and Pinto in [24], resembles, superficially at least, the do operator that Pearl uses.
Those who enjoy scholarly disputes may look to Andrew
Gelman’s blog, [25] and [26], for back-and-forth between
Pearl and Rubin disciples (Rubin himself does not seem to
participate—in that forum, at least) or to the tributes written by Pearl [27] and Heckman and Pinto [24] to the reclusive Nobel Laureate, Trygve Haavelmo, who pioneered
causal inference in economics in the 1940s in [28] and
[29]. These dialogs have been contentious at times, and
they bring to mind Sayre’s law, which says that academic
politics is the most vicious and bitter form of politics because the stakes are so low. It is this reviewer’s opinion
that the differences between these approaches to causal inference are far less important than their similarities. Sup-
Figure 4. National Transportation Safety Board inspectors
examining the self-driving Uber that killed a pedestrian in
Tempe, Arizona on March 18, 2018.
port for this includes constructions by Pearl in [3] and by
Thomas Richardson and James Robins in [30] incorporating counterfactuals into graphical cause-and-effect models,
thereby unifying various threads of the causal inference literature.
Late one afternoon in July 2018, Pearl’s co-author Dana
Mackenzie spoke on causal inference at UC Berkeley’s Simons Institute. His presentation was in the first person singular from Pearl’s perspective, the same voice used in The
Book of Why, and it concluded with an image of the first
self-driving car to kill a pedestrian. According to a report
[31] by the National Transportation Safety Board (NTSB),
the car recognized an object in its path six seconds prior
to the fatal collision. With a lead time of a second and a
half, the car identified the object as a pedestrian. When
the car attempted to engage its emergency braking system,
nothing happened. The NTSB report states that engineers
had disabled the system in response to a preponderance of
false positives in test runs.
The engineers were right, of course, that frequent,
abrupt stops render a self-driving car useless. Mackenzie
gently and optimistically suggested that endowing the car
with a causal model that can make nuanced judgments
about pedestrian intent might help. If this were to lead to
safer and smarter self-driving cars, it would not be the first
time that Pearl’s ideas led to better technology. His foundational work on Bayesian networks has been incorporated
into cell phone technology, spam filters, bio-monitoring,
and many other applications of practical importance.
Professor Judea Pearl has given us an elegant, powerful,
controversial theory of causality. How can he give his theory the best shot at changing the way we interpret data?
There is no recipe for doing this, but teaming up with science writer and teacher Dana Mackenzie, a scholar in his
own right, was a pretty good idea.
1096 NOTICES OF THE AMERICAN MATHEMATICAL SOCIETY VOLUME 66, NUMBER 7Book Review
ACKNOWLEDGMENT. This review has benefitted
from dialogs with David Aldous, Bob Anderson, Wachi
Bandera, Jeff Bohn, Brad DeLong, Michael Dempster,
Peng Ding, Tingyue Gan, Nate Jensen, Barry Mazur,
Liz Michaels, LaDene Otsuki, Caroline Ribet, Ken
Ribet, Stephanie Ribet, Cosma Shalizi, Alex Shkolnik,
Philip Stark, Lee Wilkinson, and the attendees of the
University of California, Berkeley Statistics Department
social lunch group. Thanks to Nick Jewell for informing me about scientific studies on the relationship
between exercise and cholesterol, which enhanced my
appreciation of The Book of Why.
References
[1] Silver D, Simonyan JSK, Antonoglou I, Huang A, Guez
A, Hubert T, Baker L, Lai M, Bolton A, Chen Y, Lillicrap T,
Hui F, Sifre L, van den Driessche G, Graepel T, Hassabis
D. Mastering the game of Go without human knowledge,
Nature, vol. 550, pp. 354–359, 2017.
[2] Wright S. Correlation and causation, Journal of Agricultural
Research, vol. 20, no. 7, pp. 557–585, 1921.
[3] Pearl J. Causality: Models, Reasoning, and Inference. Cambridge University Press, second ed., 2009. MR2548166
[4] Spirtes P, Glymour C, Scheines R. Causation, Prediction and
Search. The MIT Press, 2000. MR1815675
[5] Cornfield J, Haenszel W, Hammond EC, Shimkin MB,
Wynder EL. Smoking and lung cancer: recent evidence and
a discussion of some questions, Journal of the National Cancer Institute, vol. 22, no. 1, pp. 173–203, 1959.
[6] Christakis NA, Fowler JH. The spread of obesity in a large
social network over 32 years, The New England Journal of
Medicine, vol. 357, no. 4, pp. 370–379, 2007.
[7] Lyons R. The spread of evidence-poor medicine via flawed
social-network analysis, Statistics, Politics, and Policy, vol. 2,
no. 1, pp. DOI: 10.2202/2151–7509.1024, 2011.
[8] Shalizi CR, Thomas AC. Homophily and contagion are
generically confounded in observational social network
studies, Sociological Methods & Research, vol. 40, no. 2,
pp. 211–239, 2011. MR2767833
[9] Lewis M. The Undoing Project: A Friendship That Changed
Our Minds. W.W. Norton and Company, 2016.
[10] Kahneman D, Tversky A. The simulation heuristic, in
Judgment under Uncertainty: Heurisitics and Biases (D. Kahneman, P. Slovic, and A. Tversky, eds.), pp. 201–208, Cambridge University Press, 1982.
[11] Hannart A, Pearl J, Otto F, Naveu P, Ghil M. Causal
counterfactural theory for the attribution of weather and
climate-related events, Bulletin of the American Meterological Society, vol. 97, pp. 99–110, 2016.
[12] Freedman DA. Statistical models and shoe leather, Sociological Methodology, vol. 21, pp. 291–313, 1991.
[13] Freedman DA. Oasis or mirage? Chance, vol. 21, no. 1,
pp. 59–61, 2009. MR2422783
[14] Haidt J. The Righteous Mind: Why Good People Are Divided
by Politics and Religion. Vintage, 2013.
[15] Yule U. Why do we sometimes get nonsense-correlations
between time-series?–a study insampling and the nature of
time-series, Royal Statistical Society, vol. 89, no. 1, 1926.
[16] Ionnidis JPA. Why most published research findings are false, PLoS Med, vol. 2, no. 8, p. https://
doi.org/10.1371/journal.pmed.0020124, 2005.
MR2216666
[17] Oliver J. Scientific studies: Last week tonight with John
Oliver (HBO), May 2016.
[18] Lehrer J. The truth wears off, The New Yorker, December
2010.
[19] Neyman J. Sur les applications de la theorie des probabilities aux experiences agricoles: Essaies des principes.,
Statistical Science, vol. 5, pp. 463–472, 1923, 1990. 1923
manuscript translated by D.M. Dabrowska and T.P. Speed.
MR1092985
[20] Rubin DB. Estimating causal effects of treatments in randomized and non-randomized studies, Journal of Educational Psychology, vol. 66, no. 5, pp. 688–701, 1974.
[21] Rubin DB. Causal inference using potential outcomes,
Journal of the American Statistical Association, vol. 100,
no. 469, pp. 322–331, 2005. MR2166071
[22] Sekhon J. The Neyman-Rubin model of causal inference
and estimation via matching methods, in The Oxford Handbook of Political Methodology (J. M. Box-Steffensmeier, H. E.
Brady, and D. Collier, eds.), Oxford Handbooks Online,
Oxford University Press, 2008.
[23] Heckman J. The scientific model of causality, Sociological
Methodology, vol. 35, pp. 1–97, 2005.
[24] Heckman J, Pinto R. Causal analysis after Haavelmo,
Econometric Theory, vol. 31, no. 1, pp. 115–151, 2015.
MR3303188
[25] Gelman A. Resolving disputes between J. Pearl and D.
Rubin on causal inference, July 2009.
[26] Gelman A. Judea Pearl overview on causal inference,
and more general thoughts on the reexpression of existing
methods by considering their implicit assumptions, 2014.
[27] Pearl J. Trygve Haavelmo and the emergence of causal
calculus, Econometric Theory, vol. 31, no. 1, pp. 152–179,
2015. MR3303189
[28] Haavelmo T. The statistical implications of a system of
simultaneous equations, Econometrica, vol. 11, no. 1, pp. 1–
12, 1943. MR0007954
[29] Haavelmo T. The probability approach in econometrics,
Econometrica, vol. 12, no. Supplement, pp. iii–iv+1–115,
1944. MR0010953
[30] Richardson TS, Robins JM. Single world intervention
graphs (SWIGS): A unification of the counterfactual and
graphical approaches to causality, April 2013.
[31] NTSB, Preliminary report released for crash involving
pedestrian, uber technologies, inc., test vehicle, May 2018.
AUGUST 2019 NOTICES OF THE AMERICAN MATHEMATICAL SOCIETY 1097Semyon Dyatlov
Maciej Zworski
Mathematical
Theory of
Scattering
Resonances
GRADUATE STUDIES
IN M ATHEMAT I C S 200
Mathematical Theory of
Scattering Resonances
Semyon Dyatlov, University of California,
Berkeley, and MIT, Cambridge, MA, and
Maciej Zworski, University of California, Berkeley
Mathematical Theory of Scattering Resonances concentrates mostly on the simplest case of scattering by compactly supported potentials but
provides pointers to modern literature where
more general cases are studied. It also presents
a recent approach to the study of resonances on
asymptotically hyperbolic manifolds. The last
two chapters are devoted to semiclassical methods in the study of resonances.
Graduate Studies in Mathematics, Volume 200; 2019;
approximately 631 pages; Hardcover; ISBN: 978-1-47044366-5; List US$95; AMS members US$76; MAA members US$85.50; Order code GSM/200
Semyon Dyatlov
Maciej Zworski
Mathematical
Theory of
Scattering
Resonances
GRADUATE STUDIES
I N M A THE M A TI C S 200
Resonance is the Queen of the realm of waves. No
other book addresses this realm so completely and
compellingly, oscillating effortlessly between illustration, example, and rigorous mathematical discourse. Mathematicians will find a wonderful array
of physical phenomena given a solid intuitive and
mathematical foundation, linked to deep theorems.
Physicists and engineers will be inspired to consider new realms and phenomena. Chapters travel
between motivation, light mathematics, and deeper
mathematics, passing the baton from one to the other
and back in a way that these authors are uniquely
qualified to do.
—Eric J. Heller, Harvard University
Textbook
TEXTBOOK
TEXTBOOK
TEXTBOOKS
FROM THE AMSLisa R. Goldberg
Credits
Figures 1–3 are by the author.
Figure 4 is courtesy of the National Transportation Safety
Board (NTSB).
Author photo is by Jim Block.
1098 NOTICES OF THE AMERICAN MATHEMATICAL SOCIETY VOLUME 66, NUMBER 7