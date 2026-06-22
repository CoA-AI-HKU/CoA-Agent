Chatbots salute ‘Hello World’
Introducing computational linguistics and Natural Language
Processing
Aine Zhang
July 26, 2023

Contents
1 Introduction 2
1.1 Introduction to computational linguistics . . . . . . . . . . . . . . . . . . . . 2
1.2 Introduction to natural language processing (NLP) . . . . . . . . . . . . . . 3
2 Understanding the technology 3
2.1 Speech recognition . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 3
2.2 Delving into deep learning . . . . . . . . . . . . . . . . . . . . . . . . . . . . 4
2.3 Tokenization and Word Embedding . . . . . . . . . . . . . . . . . . . . . . . 5
3 Specific applications of computational linguistics 5
3.1 Chatbots that write your essays . . . . . . . . . . . . . . . . . . . . . . . . . 5
3.2 Relics of the past–archaeology . . . . . . . . . . . . . . . . . . . . . . . . . . 6
3.3 Machine translation . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 8
3.4 Your friendly neighbors physics and biology . . . . . . . . . . . . . . . . . . 8
1

1 Introduction
In recent years linguistics has crossed with many other fields to explore subjects beyond
our direct experience in communication. Particularly considering the endless possibilities
of computer science and artificial intelligence, linguistics is being used to develop complex
communication skills in robots. We can talk to virtual assistants, generate paragraphs from
bots, and artificially interpret texts written by other people or robots. These technology are
entwined with basic linguistic concepts such as syntax and morphology that help robots learn
languages by themselves. Majors like Stanford University’s Symbolic Systems Program com-
bine linguistics with computer science, statistics, psychology, philosophy etc. These majors
focus on systems that are built with or work with symbols–from natural languages to minds
and brains to social systems. 1 These are just some examples of the things computational
linguistics studies, not to mention trending discussions in natural language processing.
1.1 Introduction to computational linguistics
Computational linguistics is ‘the scientific and engineering discipline concerned with un-
derstanding written and spoken language from a computational perspective, and building
artifacts that usefully process and produce language, either in bulk or in a dialogue setting.’
It is aimed to formulate frameworks for languages in ways enabling computationally tractable
implementations of syntactic and semantic analysis. 2
Words are divided into nouns, verbs, adjectives and such. Linguistic analysis use these
terms a lot already, and the syntactical structure is quite well studied. However, adapting
it to computers is not so simple.
For example, generating a sentence in English using the syntactical structure ‘adjective
+ subject + verb’ does not mean that the sentence will make sense. So analysis of patterns
of words that ‘make sense’ when grouped together may yield interesting results when com-
puters can process countless examples together. A typical example 3 would be the sentence
‘colorless green ideas sleep furiously’, composed by Noam Chomsky in his 1957 book Syn-
tactic Structures. The sentence itself is grammatically correct, but semantically nonsensical.
No obvious meaning can be derived from this sentence (however poetic it is), and it shows
the inadequacy of certain probabilistic models of grammar, demanding need for more struc-
ture models. This is just one problem among countless for computer scientists that design
models.
Based on these problems, scientists realized that allowing the program itself to figure
out what makes sense and what does not greatly improves efficiency–you can’t really teach
programs all the rules, they cannot learn like babies after all.
1. “Stanford Symbolic Systems Progam,” (online), 2023, https://symsys.stanford.edu/.
2. Lenhart Schubert, “Computational Linguistics,” ed. Edward N. Zalta, 2020, https://plato.stanford.
edu/archives/spr2020/entries/computational-linguistics/.
3. here supplemented by a kind reviewer
2

1.2 Introduction to natural language processing (NLP)
Natural language processing (further abbreviated as NLP) is the study of mathematical
and computational modeling of various aspects of language and the development of a wide
range of system.4 It specifically aims to build software that can manipulate human languages,
considering both deep understanding and text generation. Technology related to NLP include
machine translation, text generators (which did not generate this text), chatbots, cooperative
databases etc.
NLP is also highly interdisciplinary, crossing areas such as computer science, psychology,
logic, cryptology, and more. It is important to note that NLP is considered as a sub-field of
artificial intelligence (AI), but not necessarily a branch of computational linguistics.
Now you might say ‘NLP and computational linguistics sound very similar, what’s the
real differentiating factor?’ The answer is that they have different goals. Computational
linguistics focuses on ‘the system or concept that machines can be computed to understand,
learn, or output languages.’ In contrast, NLP focuses on computer understanding of language
in order to make programs speak or write.
2 Understanding the technology
The technology behind many crucial tools in computational linguistics has also improved
largely. Combining linguistics elements with computer science means that we also have to
know the basic logic behind programs that use linguistics. Some linguistic studies simply
use already existing tools to facilitate analysis, while other studies (like NLP) aim to truly
cross the two fields by using distinct features in them. We will first talk about technical
elements, so that these terms can be better referenced when discussing linguistic aspects.
2.1 Speech recognition
Specifically for speech based AI models, speech recognition is the first step to take. This
is essentially a speech-to-text conversion, and the most common model used is the Hidden
Markov Model(HMM). This model is used in both Alexa and Siri, two of the most popular
voice assistants. It essentially breaks down your talk into small units, and it will figure
out the phonemes 5 uttered in each second. The program figures out what you mean by
comparing your combination of phonemes (words or phrases) with statistics of common sets
of words and sentences.6 Some processes may be largely based on data sets of human speech,
while others have systematic linguistic frameworks applied to facilitate the recognition.
As we get more adept at speech recognition, it can accommodate more languages and
dialects based off statistics. Currently speech recognition can divide words from unknown
languages, and it can also recognize dialects like the Sichuan dialect.
4. Aravind J. Joshi, “Natural Language Processing,” Science 253, no. 5025 (1991): 1242–1249, issn:
00368075, 10959203, accessed June 28, 2023, http://www.jstor.org/stable/2879169.
5. A phoneme is the smallest unit of speech
6. “Natural Language Processing - Overview,” accessed June 30, 2023, https://www.geeksforgeeks.org/
natural-language-processing-overview/.
3

In this process, speech recognition uses a technique called ‘deep learning’, which will be
discussed in the next subsection.
2.2 Delving into deep learning
Deep learning is a subset of machine learning, which is essentially a neural network with
three or more layers.7 Now this may sound extremely complicated (and don’t get me wrong
it actually is), but put simply, deep learning aims to teach computers to learn from examples.
Think of your own language learning process, you learn to speak languages by the exam-
ples your environment (your family, perhaps) gives you. It turns out that if we get computers
to learn the same way, computers can generate results with extremely high accuracy.
Say, if we want a deep learning program to study English, then we would give it an
enormous amount of English texts to study.
However, what if the program needs to study a language that is almost dying? There
might not be a data set large enough for the program to formulate an accurate, comprehensive
understanding of the language. Thus, we can get the program to learn until it generates a
result we deem accurate, and feed this back into the program to artificially expand our data
set.
Deep learning uses neural networks, modeled loosely on the human brain. These networks
consist of thousands or millions of nodes that are densely interconnected. Data is sent
through nodes, and nodes are layered so that data is ‘knitted’ together while other factors
are adjusted to produce satisfactory results.8 In the diagram below, we can see how a simple
network works. Input goes in on the left, neurons in the middle process and interpret it,
while it is then produced on the right. 9
Alternatively, if you’re familiar with statistics, psychology or in general just the common
experimental process, neural networks work like a regression line. In certain experiments,
when you have certain data graphed on a scatter plot, you want to conclude a formula for
a line of best fit to try and interpret the data. You would want the formula to be able to
7. Eda Kavlakoglu, “AI vs. Machine Learning vs. Deep Learning vs. Neural Networks: What’s the Differ-
ence?,” May 27, 2020, accessed June 29, 2023, https://www.ibm.com/cloud/blog/ai-vs-machine-learning-
vs-deep-learning-vs-neural-networks.
8. Larry Hardesty, “Explained: Neural networks,” April 14, 2017, accessed June 28, 2023, https://news.
mit.edu/2017/explained-neural-networks-deep-learning-0414.
9. If you feel like tinkering around with a neural network, feel free to visit https://playground.tensorflow.org
4

predict values with different variables in the same experiment. Neural network adds data to
the plot, and recalculates the best-fit line to predict data more accurately.
2.3 Tokenization and Word Embedding
After breifly introducing machine learning, we can further go into inputting data into algo-
rithms.
In any NLP program, tokenization is the first step. It breaks natural language into small
bits of information that can be considered discrete elements. This can then be marked as
numerical data that machines can easily understand.
Word embedding is an important approach to representing words and documents. It
is essentially a numeric vector input that represents a word, and it groups similar words
together so they have a similar representation. This can be used as input in NLP deep
learning models. Words deemed important to learning is taken from its text, given a numeric
representation, and it can then be used in training or reference. It extracts features from the
text to train programs. One of the most popular techniques is called Bag of Words (BoW).
The first step of BoW is tokenization, where sentences are extracted from the text and words
are then extracted from sentences. Stop words and punctuation are removed, all remaining
words are given numeric representation and moved into a data set that the program can
learn from.
In some ways I think of this as a juice production line, where the peel is first removed
from a fruit, then the pulp is extracted. Seeds and other unwanted substances are removed,
and we can add this into a processing room where all of the ‘essence’ is finally manufactured
into something we want.
On the contrary, if we compare this to a human learning process, children learning lan-
guages also take out important information and group them together. But these information
form natural groups in our consciousness instead of being given numeric representation.
3 Specific applications of computational linguistics
Computational linguistics is applied to many different fields in attempt to explain phenomena
related to language structures. It is not restricted to traditional linguistic analysis and field
studies, but it can also be used in fields ranging from social sciences to natural sciences.
3.1 Chatbots that write your essays
Influential NLP models include Eliza, Tay, ChatGPT, LaMDA, Siri, Alexa, MoE, and BERT
(and his Muppet friends). Some of these models are closely connected with our lives, while
others might have served as prototypes for following versions.
• Eliza: Eliza was developed in the 1960s, and it tried to solve the Turing Test–trying to
confuse people with whether they’re talking to a robot or another person (for record,
certain human beings did not pass the Turing Test, so beware of human-like bots
lurking near you).
5

• Tay: Tay was launched by Microsoft in 2016, and it aimed to navigate Twitter by
learning from other users. Unfortunately, Tay was deactivated after it learned to post
(((( hhhhmemes hate comments.
• Siri and Alexa: Calling their names will wake these two virtual assistants, respectively
developed by Apple and Amazon. Siri debuted in 2011 with the unveiling of the iPhone
43s, and Alexa followed closely by debuting in 2014. Both of these models use a Hidden
Markov Model10(described in the subsection ‘Natural language understanding’).
• MoE (Mixture of Experts): Different from other deep learning tools, MoE models aim
to provide different parameters for different inputs. 11 It uses a ‘divide and conquer’
method that breaks tasks into subtasks (much like British colonial history) to process
large tasks.
• LaMDA (Language Model for Dialogue Advanced Placement Applications): LaMDA
was published in 2020 by Google, and it was not widely applied to use in the public.
Following the announcement of ChatGPT, LaMDA never really got to face the crowds
at all.
• GPT (Generative Pre-Trained Transformer): Perhaps being the most well-known NLP
model currently, ChatGPT was developed by OpenAI in 2022 and has the ability to
write fluent prose in multiple languages. Unfortunately, ChatGPT ‘flunked’ both AP
Language and Composition and AP Literature while crushing almost all other AP
courses, reflecting a gap in ability for current models (while also meaning that English
majors get the last laugh).
• BERT and his muppet friends: These machine learning models generate fluent writing.
This breed of language AIs is based off Sesame Street (also known as the Muppets),
an American educational television series for children. This trend started with ELMo,
developed by the Allen Institute and published in 2017. 12
3.2 Relics of the past–archaeology
Computational linguistics combined with archaeology can also yield many new perspectives
on decoding the past. Programs can recognize hieroglyphics, oracle bone scripts, unusual
patterns in artifacts, and many more. Especially relating to linguistics, computers can be
used to analyze structures and crack unknown languages.
For example, computational analysis was applied to the dead sea scrolls–which included
some of the earliest versions of the Old Testament (the Hebrew Bible). However, ancient
10. “NLP: The magic behind popular voice assistants Alexa and Siri,” 2021, https://innovention.io/nlp-
magic-behind-popular-voice-assistants-alexa-siri/.
11. “A Complete Guide to Natural Language Processing,” January 11, 2023, accessed June 30, 2023, https:
//www.deeplearning.ai/resources/natural-language-processing/.
12. James Vincent, “Why are so many AI systems named after the Muppets?,” (online), December 11,
2019, accessed June 29, 2023, https://www.theverge.com/2019/12/11/20993407/ai- language- models-
muppets-sesame-street-muppetware-elmo-bert-ernie.
6

Figure 1: ELMo, BERT, Grover, Big BIRD, Rosita, RoBERTa, ERNIE, ERNIE2.0, and KERMIT.
A CPU-warming cartoon for aging computers.
scrolls were hard to preserve, and these scrolls were mainly composed of fragments that were
extremely hard to combine and . The scrolls were recorded in Hebrew, but the writer(s)
is (are) currently unknown. Recent research uses ‘computers to analyse digital images of
the scroll text and identify tiny differences in handwriting that are unique to individuals–a
method known as digital paleography.’13
In addition, analysis of Mary Queen of Scots Codes were completed by using AI identi-
fication and GUI (graphic user interface) tools. Long story short, Queen Mary’s long lost
letters were uncovered, but they needed to be decoded and the language of the letters were
not known. Thus, modern cryptologists used GUI tools to firstly identify different symbols
that ciphered the text. Then they ran the symbols through mass testing Italian and French.
Clear French words were deciphered, and they were able to gradually decode the letters they
obtained.14
Similar technology is used to identify, transcribe and translate oracle bone scripts from
ancient China. In order to utilize advanced machine learning methods to automatically
process oracle scripts, scholars constructed an information system to symbolize, serialize
and store related data. 15
13. Anna Salleh, “Who wrote the Dead Sea Scrolls? Digital handwriting analysis and artificial intelligence
offer new clues.,” April 22, 2021, accessed June 30, 2023, https://www.abc.net.au/news/science/2021-04-
22/dead-sea-scrolls-artificial-intelligence-handwriting-analysis/100083866#: ∼:text=The%20idea%20was%
20to%20use%20computers%20to%20analyse, individuals%20%E2%80%93%20a%20method%20known%
20as%20digital%20palaeography.
14. George Lasry, Norbert Biermann, and Satoshi Tomokiyo, “Deciphering Mary Stuart’s lost letters from
1578-1584,” Cryptologia 47, no. 2 (2023): 101–202, https://doi.org/10.1080/01611194.2022.2160677.
15. Han Xu et al., “Proceedings of the 2020 Conference on Empirical Methods in Natural Language Pro-
7

Figure 2: Letters of Queen Mary, red bracketed words indicate clear identification of Middle French
words.
3.3 Machine translation
Natural language processing can also be used to conduct machine translation.
Machine translation is an older technology compared to text generation, but it is con-
stantly improving in accuracy. Popular translation tools include Bing Translator and Google
Translate. Google translate uses English as an interlingua through a phrase-based machine
translation process, while Bing Translator is based on statistical methods. 16
Currently machine translation can be conducted between almost any major languages.
Dialects and a lot of smaller languages can also be translated, but there are language groups
that haven’t yet been incorporated.
This has also triggered a career crisis for those studying in translation majors. How-
ever, current machine translation tools only serve as aid to human translators. Inability to
read implied meaning and lack of understanding in emotional tone may hinder accuracy in
translation for computer programs.
3.4 Your friendly neighbors physics and biology
While computational linguistics is not usually applied to natural sciences, new research is
being done on other subjects that use computational linguistics as a framework.
Quantum physics can be related to linguistics. While they may seem unrelated, both
concern ‘comprehensive reasoning about the way information flows among subsystems and
the manner in which this flow gives rise to the properties of a system as a whole. 17 These
processes are largely related to computation, and categorical methods introduced by quantum
information can be applied to natural languages.
Biomolecules can also be related to computational linguistics. Computer science can
provide ‘theoretical tools and formalisms’ to apply concepts in biology to language process-
cessing: System Demonstrations,” 2020, 227–233, https://doi.org/10.18653/v1/2020.emnlp- demos.29,
https://aclanthology.org/2020.emnlp-demos.29/.
16. Schubert, “Computational Linguistics.”
17. Chris Heunen, Mehrnoosh Sadrzadeh, and Edward Grefenstette, Quantum Physics and Linguistics: A
Compositional, Diagrammatic Discourse (Oxford University Press, February 2013), isbn: 9780199646296,
https://doi.org/10.1093/acprof:oso/9780199646296.001.0001.
8

ing.18 Furthermore, NLP models can be used to analyze sequences in DNA and protein
molecules. An important approach in NLP is word embedding (introduced previously), and
word embedding can be used to identify N4-methylcytosine—a specific biochemical alter-
ation of DNA. This can be used to formulate a separate deep learning algorithm, which can
help in affecting genetic operations. 19 A great example of just the combination of linguistics
and biology can be seen in IOL’s problem 4 of 2010, which discusses mRNA sequences and
their following polypeptide. This specific example does not use computer science, but it
demonstrates practices in modern technology that do.
Figure 3: IOL 2010 Stockholm
18. Jim´ enez L´ opez and M. Dolores, “Processing Natural Language with Biomolecules: Where Linguistics,
Biology and Computation Meet,” in Revolutions and Revelations in Computability , ed. Ulrich Berger et al.
(Cham: Springer International Publishing, 2022), 139–150.
19. Abdul Wahab et al., “Deciphering Mary Stuart’s lost letters from 1578-1584,” Cryptologia 11, no. 2
(2021): 2045–2322, accessed July 2, 2023, https://doi.org/10.1038/s41598-020-80430-x.
9

References
“A Complete Guide to Natural Language Processing,” January 11, 2023. Accessed June 30,
2023. https://www.deeplearning.ai/resources/natural-language-processing/.
Hardesty, Larry. “Explained: Neural networks,” April 14, 2017. Accessed June 28, 2023.
https://news.mit.edu/2017/explained-neural-networks-deep-learning-0414.
Heunen, Chris, Mehrnoosh Sadrzadeh, and Edward Grefenstette. Quantum Physics and Lin-
guistics: A Compositional, Diagrammatic Discourse. Oxford University Press, February
2013. isbn: 9780199646296. https://doi.org/10.1093/acprof:oso/9780199646296.001.
0001.
Joshi, Aravind J. “Natural Language Processing.” Science 253, no. 5025 (1991): 1242–1249.
issn: 00368075, 10959203, accessed June 28, 2023. http : / / www . jstor . org / stable /
2879169.
Kavlakoglu, Eda. “AI vs. Machine Learning vs. Deep Learning vs. Neural Networks: What’s
the Difference?,” May 27, 2020. Accessed June 29, 2023. https://www.ibm.com/cloud/
blog/ai-vs-machine-learning-vs-deep-learning-vs-neural-networks.
Lasry, George, Norbert Biermann, and Satoshi Tomokiyo. “Deciphering Mary Stuart’s lost
letters from 1578-1584.” Cryptologia 47, no. 2 (2023): 101–202. https://doi.org/10.
1080/01611194.2022.2160677.
L´ opez, Jim´ enez, and M. Dolores. “Processing Natural Language with Biomolecules: Where
Linguistics, Biology and Computation Meet.” In Revolutions and Revelations in Com-
putability, edited by Ulrich Berger, Johanna N. Y. Franklin, Florin Manea, and Arno
Pauly, 139–150. Cham: Springer International Publishing, 2022.
“Natural Language Processing - Overview.” Accessed June 30, 2023. https://www.geeksfor
geeks.org/natural-language-processing-overview/.
“NLP: The magic behind popular voice assistants Alexa and Siri,” 2021. https://innovention.
io/nlp-magic-behind-popular-voice-assistants-alexa-siri/.
Salleh, Anna. “Who wrote the Dead Sea Scrolls? Digital handwriting analysis and artificial
intelligence offer new clues.,” April 22, 2021. Accessed June 30, 2023. https://www.abc.
net.au/news/science/2021-04-22/dead-sea-scrolls-artificial-intelligence-handwriting-
analysis/100083866#:∼:text=The%20idea%20was%20to%20use%20computers%20to%
20analyse,individuals%20%E2%80%93%20a%20method%20known%20as%20digital%
20palaeography.
Schubert, Lenhart. “Computational Linguistics.” Edited by Edward N. Zalta, 2020. https:
//plato.stanford.edu/archives/spr2020/entries/computational-linguistics/.
“Stanford Symbolic Systems Progam.” (online), 2023. https://symsys.stanford.edu/.
Vincent, James. “Why are so many AI systems named after the Muppets?” (online), De-
cember 11, 2019. Accessed June 29, 2023. https://www.theverge.com/2019/12/11/
20993407/ai-language-models-muppets-sesame-street-muppetware-elmo-bert-ernie.
10

Wahab, Abdul, Hilal Tayara, Zhenyu Xuan, and Kil ToA Chong. “Deciphering Mary Stuart’s
lost letters from 1578-1584.” Cryptologia 11, no. 2 (2021): 2045–2322. Accessed July 2,
2023. https://doi.org/10.1038/s41598-020-80430-x.
Xu, Han, Yuzhuo Bai, Keyue Qiu, Zhiyuan Qiu, and Maosong Sun. “Proceedings of the 2020
Conference on Empirical Methods in Natural Language Processing: System Demonstra-
tions,” 2020, 227–233. https://doi.org/10.18653/v1/2020.emnlp- demos.29. https:
//aclanthology.org/2020.emnlp-demos.29/.
11