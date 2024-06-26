
# A RAG-based system for Pubmed

## Table of Contents
  - [Overview](#overview)
  - [Data Preparation](#data-preparation)
    - [Data Collection](#data-collection)
    - [Data Chunking](#data-chunking)
    - [Data Embedding](#data-embedding)
    - [Data Storage](#data-storage)
  - [Information Retrieval](#information-retrieval)
  - [User Interface](#user-interface)
  - [Text Generation](#text-generation)
  - [Evaluation Metrics](#evaluation-metrics)
    - [Evalutaion of the first Data Set](#evalutaion-of-the-first-data-set)
        - [BLEU Scores Test Set 1](#bleu-scores-test-set-1)
        - [ROUGE Scores Test Set 1](#rouge-scores-test-set-1)
        - [BERT Scores Test Set 1](#bert-scores-test-set-1)
  - [Test Dataset Generation Approach 1](#test-dataset-generation-approach-1)
    - [Question Generation Process](#question-generation-process)
    - [Records to the Initial Test Set](#records-to-the-initial-test-set)
    - [Generating the Labeled Test Set](#generating-the-labeled-test-set)
  - [Test Dataset Generation Approach 2](#test-dataset-generation-approach-2)
  - [Contributions](#contributions)
    - [Abdulghani Almasri](#abdulghani-almasri)
    - [Paul Dietze](#paul-dietze)
    - [Mahammad Nahmadov](#mahammad-nahmadov)
    - [Sushmitha Chandrakumar](#sushmitha-chandrakumar)

## Overview
<div style="text-align:center"><img src="images/RAG.png" /></div>

The architecture of the project consists of four components that are containerized in [`Docker`](https://www.docker.com/) containers and interconnected using [`Docker`](https://www.docker.com/) internal network that is also accessible using the local host computer. The four components are as follows:

- Front-end web interface to receive user queries, powered by [`Svelte`](https://svelte.dev/) framework
- Middleware powered by [`FastAPI`](https://fastapi.tiangolo.com/) to retrieve the documents from [`OpenSearch`](https://opensearch.org/), filter them, send a prompted question to LLM, process the reply from the LLM and send it back to the user
- [`OpenSearch`](https://opensearch.org/) for document and vector storage, indexing and retrieval

To the run the project for testing, please follow the steps in the [`installation_instructions.md`](installation_instructions.md)


## Data Preparation

### Data Collection

The traditional [`E-utilities`](https://www.ncbi.nlm.nih.gov/books/NBK25499/) are the usual tool to collect data from [`PubMed`](https://pubmed.ncbi.nlm.nih.gov/) website, but these tools allow a maximum of 10000 records to be retrieved in a search request. On the other hand, the number of the abstracts to be collected for this project is in the range of 59000 and this number of abstracts cannot be downloaded using the traditional tools, therefore we used the [`EDirect`](https://www.ncbi.nlm.nih.gov/books/NBK179288/) tool on the Unix command line as it does not have this limitation. 

Under [`EDirect`](https://www.ncbi.nlm.nih.gov/books/NBK179288/) there are two commands that we used to retrieve the records from [`PubMed`](https://pubmed.ncbi.nlm.nih.gov/),  `esearch` which is used to search for the abstracts within a specific time range and specific keywords, and `efetch` which retrieve the actual records found by `esearch`. 

> We tried to pipeline `efetch` after `esearch` directly to download the records from [`PubMed`](https://pubmed.ncbi.nlm.nih.gov/) but that did not work properly, so we used `esearch` to search for and store the article IDs of all article that have the word `intelligence` in the abstract or in the title of the article as indicated in the project specifications, we then used `efetch` separately to download the articles using the article IDs we collected using `esearch`, in this second stage we excluded any article outside the time range between 2013 and 2023.

[`EDirect`](https://www.ncbi.nlm.nih.gov/books/NBK179288/) commands used to retrieve the article IDs:

```PowerShell
esearch -db pubmed -query "intelligence [title/abstract] hasabstract" | efetch -format uid >articles_ids.csv
```

The article IDs in [`articles_ids.csv`](articles_ids.csv) are then used as an input to the Python script [`retrieve_pubmed_data.py`](data_preprocessing/retrieve_pubmed_data.py) for the actual retrieval of articles, inside this script we used `efetch` in the following format:

 ```Python
 Entrez.efetch(db="pubmed", id=idlist[i:j], rettype='medline', retmode='text')
 ```


### Data Chunking

To comply with the maximum sequence length of both the embedding and the LLM models, and to provide a diverse and granular context, the abstracts had to be chunked into smaller pieces before they are indexed and stored in OpenSearch. We also left an overlap margin between subsequent chunks to keep the context connected and more natural. We experimented with multiple chunk sizes 500, 800 and 100 characters and multiple overlap windows 100, 200 and 250 and we ended up using the chunk size of 500 characters and am overlap windows of 200 as it provided the best retrieval performance compared to the other options. This could be attributed to the fact that smaller chunks can generate more accurate embeddings as the mean pooling is restricted to a shorter list of tokens. 

For chunking, we used `RecursiveCharacterTextSplitter` in [`LangChain`](https://python.langchain.com/docs/modules/data_connection/document_transformers/recursive_text_splitter)

```Python
    # Initialize langChain splitter to split abstracts
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap, separators=["\n\n", "\n", " ", ""])

    # Chunking the abstract with the splitter
    chunks = text_splitter.split_text(str(row['Abstract']))
```

The chunking is done using the script [`data_chunking.py`](data_preprocessing/data_chunking.py) which takes the abstracts we downloaded from [`PubMed`](https://pubmed.ncbi.nlm.nih.gov/), chunk them and save them in a new CSV file.

### Data Embedding

We chose the [`Universal AnglE Embedding`](https://huggingface.co/WhereIsAI/UAE-Large-V1) as our embedding model because it is listed 6th on the [`MTEB Leaderboard`](https://huggingface.co/spaces/mteb/leaderboard) with a retrieval performance close to a much larger models. The size of this model is just 1.34 GB which make it suitable to run locally without the need for any subscription or remote API calls. The model provides two separate embedding options, a standard option to embed the document to be retrieved and a customized option that is augmented with a prompt to generate a query embedding that is more appropriate for retrieval tasks. 

```Python
from angle_emb import AnglE

# Document embedding
angle = AnglE.from_pretrained('WhereIsAI/UAE-Large-V1', pooling_strategy='cls').cuda()
vec = angle.encode('hello world', to_numpy=True)

# Query embedding
angle = AnglE.from_pretrained('WhereIsAI/UAE-Large-V1', pooling_strategy='cls').cuda()
angle.set_prompt(prompt=Prompts.C)
vec = angle.encode({'text': 'hello world'}, to_numpy=True)
```

We created the Python script [`data_embedding.py`](data_preprocessing/data_embedding.py) that takes the CSV file of the chunks we generated in the previous step and generate the embeddings for those chunks and store the output in a new CSV file, we utilized [`Google Colab`](https://colab.google/) for this step as it is requires a GPU to finish in an acceptable time, we repeated this process for the different chunk sizes we experimented with. 


> We have created a new embedding class for [`Universal AnglE Embedding`](https://huggingface.co/WhereIsAI/UAE-Large-V1) model as it is natively supported by [`LangChain`](https://www.langchain.com/), we implemented this new functionality in [`models.py`](app/middleware/models.py).
 
### Data Storage

To store the data with their embeddings in [`OpenSearch`](https://opensearch.org/) we created an index with k-NN enabled and we defined the data types mapping as in the snippet below. 

```yml
    index_mapping = {
        "settings": {
            "index": {
            "knn": True,
            "knn.algo_param.ef_search": 100
            }
        },
        "mappings": {
            "properties": {
                "pmid": {
                    "type": "integer"
                },
                "title": {
                    "type": "text"
                },
                "chunk_id": {
                    "type": "integer"
                },
                "chunk": {
                    "type": "text"
                },
                "year": {
                    "type": "integer"
                },
                "month": {
                    "type": "integer"
                },
                "embedding": {
                    "type": "knn_vector",
                    "dimension": 1024,
                    "method": {
                        "name": "hnsw",
                        "engine": "lucene"
                    }                
                },
                "vector_field": {
                    "type": "alias",
                    "path" : "embedding"
                }
            }
        }
    }
```

We used [`lucene`](https://opensearch.org/docs/latest/search-plugins/knn/knn-index/) as an approximate k-NN library for indexing and search with the method [`hnsw`](https://opensearch.org/docs/latest/search-plugins/knn/knn-index/) for k-NN approximation.

> We created an alias for the vector field to keep using the default name `vector_field` in addition to the customized name we chose `embedding` because [`LangChain`](https://www.langchain.com/) libraries seem to recognize the default name only!


## Information Retrieval

All access to the [`OpenSearch`](https://opensearch.org/) backend is carried out through the [`LangChain`](https://www.langchain.com/) vector store interface [`OpenSearchVectorSearc`](https://api.python.langchain.com/en/v0.0.345/vectorstores/langchain.vectorstores.opensearch_vector_search.OpenSearchVectorSearch.html) in which we used [`Universal AnglE Embedding`](https://huggingface.co/WhereIsAI/UAE-Large-V1) defined in `AnglEModel()` as an embedding function, we also used the default login credentials of [`OpenSearch`](https://opensearch.org/) and disabled any security related messages as they are relevant to our project.


```Python
from langchain_community.vectorstores import OpenSearchVectorSearch

os_store = OpenSearchVectorSearch(
    embedding_function=AnglEModel(),
    index_name=index_name,
    opensearch_url="https://opensearch:9200",
    http_auth=("admin", "admin"),
    use_ssl=False,
    verify_certs=False,
    ssl_assert_hostname=False,
    ssl_show_warn=False,
)
```

Before a vector store can be used by [`LangChain`](https://www.langchain.com/) in the RAG pipeline it has to be wrapped in a retriever object that defines the parameters to be used in the retrieval process such as the number of the top k documents to consider, the text and vector fields in [`OpenSearch`](https://opensearch.org/) index and whether you would like to apply any filters on the retrieved documents based on the meta data. 

```Python
retriever = vector_store.as_retriever(search_kwargs={"k": 3, "text_field":"chunk", "vector_field":"embedding"})
```

We encapsulated the creation of vector store through the helper functions that can be found in the utilities module [`utils.py`](app/middleware/utils.py)

### Metadata filtering after retrieval 

Implementing metadata filtering requires extending the built-in `VectorStoreRetriever` class from [`LangChain`](https://www.langchain.com/), as there's no built-in solution for metadata filtering in [`LangChain`](https://www.langchain.com/). The extension located in [`models.py`](app/middleware/models.py) allows for a custom filtering mechanism based on metadata such as titles, years, and keywords.

``` Python 
from langchain_core.vectorstores import VectorStoreRetriever

class VariableRetriever(VectorStoreRetriever):
    def __init__(self, vectorstore, retrieval_filter):
        self.vectorstore = vectorstore
        self.retrieval_filter = retrieval_filter

    def get_relevant_documents(self, query: str):
        # Retrieve documents based on query
        results = self.vectorstore.get_relevant_documents(query)
        # Filter documents based on metadata
        filtered_results = self.retrieval_filter.apply(results)
        return filtered_results

```

The filtering logic as well as the criteria by which a set of documents should be filtered is encapsulated by the `RetrievalFilter` ([`models.py`](app/middleware/models.py)).

## User Interface

The final iteration of our user interface employs the [`Svelte`](https://svelte.dev/) framework, a modern frontend compiler, 
which enhances the development experience by offering a simpler and more intuitive syntax compared to traditional frameworks. This decision was made because it is one of the most popular and modern frameworks currently used. Unlike frameworks that use a Virtual DOM, Svelte compiles components to highly efficient imperative code that updates the DOM when the state of the application changes. This results in faster initial loads and smoother runtime performance.

### File Descriptions

The frontend code consists of 2 files: [`App.svelte`](app/frontend/src/App.svelte) and [`Chatbot.svelte`](app/frontend/src/Chatbot.svelte). The latter contains almost all of the frontend logic, layout and styling.

#### Layout

- The application features a centralized chat interface (`#chat-container`) against a background image (`/images/medicine.jpg`), providing a thematic context.
- Messages are displayed in a scrollable container (`#chat-messages`), enhancing readability and user engagement.
- A dedicated input area (`#user-input-container`) allows users to type messages, with a send button (`#send-button`) to submit queries.
- Filter controls (`#filter-controls`) are optionally displayed, allowing the user to refine searches by title, year range, and keywords. These controls are toggled via a checkbox (`#filter-switch`).


#### Endpoints

- **Server Status Check**: Periodically checks the server status at `http://localhost:8000/server_status` and updates the UI based on the server's availability.
- **Message Sending to Backend**: Sends user messages along with optional filters (title, year range, keywords) to `http://localhost:8000/retrieve_documents_dense_f` for processing and retrieval of relevant documents.


#### Features

- **Dynamic Message Handling**: Users can send messages which are then processed by the backend, with the responses including potential references displayed dynamically.
- **Interactive UI Elements**: The UI provides interactive elements like toggling filter visibility, sending messages, and displaying server status, enhancing user interaction.
- **Extracting and Displaying References**: Extracts references from the backend's response and displays them as clickable links after the response message, facilitating easy access to source documents.
- **Real-time Server Status Monitoring**: Continuously monitors the server status, displaying a message about the current status.
- **Filtering Capability**: Offers users the ability to filter their search queries by title, year range, and keywords, which can be toggled on or off.


### Screenshots
Here are some screenshots of the frontend interface to give you a glimpse of what to expect:
<div style="text-align:center"><img src="images/screen1_new.png" /></div>
<div style="text-align:center"><img src="images/screen2_new.png" /></div>
<div style="text-align:center"><img src="images/screen4_new.png" /></div>

## Text Generation

We experimented using multiple large language models like [`Llama 2`](https://huggingface.co/meta-llama), [`OpenAI`](https://openai.com/blog/openai-api), and [`Phi-2`](https://huggingface.co/microsoft/phi-2) using both the local and hosted options, but because of the resource limitations and the requirements for credit cards we ended up using the [`Falcon-7B-Instruct`](https://huggingface.co/tiiuae/falcon-7b-instruct) model because the inference API is free of charge and publicly available on [`HuggingFace`](https://huggingface.co/) without any requirements other that the API token. To access the inference API we can use `HuggingFaceHub` or [`HuggingFaceEndpoint`](https://python.langchain.com/docs/integrations/llms/huggingface_endpoint) interface provided by [`LangChain`](https://www.langchain.com/)

We initialized the model with very low temperature as we are interested in the factual nature of the answer more than its randomness, we also limited the length of the answer to a 500 tokens to keep it more convenient for reading.

```Python    
repo_id = "tiiuae/falcon-7b-instruct" 
llm = HuggingFaceHub(
    repo_id=repo_id, model_kwargs={"temperature": 0.01, "max_new_tokens": 500}
)   
```

> We used the old `HuggingFaceHub` interface instead of the new [`HuggingFaceEndpoint`](https://python.langchain.com/docs/integrations/llms/huggingface_endpoint) because it is still not stable and not working properly

We built a [`LangChain`](https://www.langchain.com/) RAG pipeline using the chain [`RetrievalQA`](https://api.python.langchain.com/en/latest/chains/langchain.chains.retrieval_qa.base.RetrievalQA.html) as in the snippet below:

```Python
# Loads the latest version of RAG prompt
prompt = hub.pull("rlm/rag-prompt", api_url="https://api.hub.langchain.com")

# Initialize langChain RAG pipeline
rag_pipeline = RetrievalQA.from_chain_type(
    llm=llm,
    chain_type="stuff",
    retriever=retriever,
    return_source_documents=True,
    chain_type_kwargs={"prompt": prompt, "verbose":"True"},
    verbose=True    
)
```

As shown above, we used the most up-to-date RAG prompt provided by [`LangChain`](https://www.langchain.com/) that can be downloaded from [`LangChain`](https://www.langchain.com/) hub `rlm/rag-prompt`. We used a `chain_type` of `stuff` to use all the documents retrieved from [`OpenSearch`](https://opensearch.org/) as a context in the answer generation process, in addition to that we configured the RAG pipeline to return the source documents used in the answer generation to use their metadata in following steps like constructing the URLs of the original articles in [`PubMed`](https://pubmed.ncbi.nlm.nih.gov/) that will be provided to the user as sources.



## Evaluation Metrics

The difference in the scores between evaluation metrics such as BERTScore, BLEU Score, and ROUGE-L F1 score is expected because each metric evaluates different aspects of the generated text and has different scoring mechanisms. Let's briefly discuss each metric:


1. ### BLEU Score: 
   BLEU (Bilingual Evaluation Understudy) Score is a metric commonly used for evaluating the quality of machine-translated text. It measures the n-gram overlap between the generated text and the reference text. BLEU Score ranges from 0 to 1, where higher scores indicate higher similarity between the generated and reference text. However, BLEU Score is known to have limitations, such as not considering word order or semantic similarity, which can lead to lower scores compared to other metrics.

2. ### ROUGE Score: 
   ROUGE (Recall-Oriented Understudy for Gisting Evaluation) is a family of metrics used for evaluating the quality of summarization and machine-generated text. ROUGE-L specifically measures the longest common subsequence (LCS) between the generated text and the reference text, focusing on content overlap. The F1 score is computed based on precision and recall, where higher scores indicate better overlap between the generated and reference text.

3. ### BERTScore:
    BERTScore is a metric that measures the similarity between two sentences using contextual embeddings from a pre-trained BERT model. It computes the F1 score based on the precision and recall of the overlapping n-grams between the reference and predicted sentences. BERTScore typically produces higher scores when the generated text closely matches the reference text in terms of semantics and fluency.

Each metric has its own strengths, weaknesses, and scoring criteria, which can lead to variations in the scores obtained for the same generated text. Therefore, it's normal to observe differences in the scores between these evaluation metrics. It's important to consider the specific characteristics of each metric and interpret the scores in context to understand the quality of the generated text comprehensively.

### Evalutaion of the first Data Set
Here we talk about the evalutation of the main test-set that contains 741 questions total.
```Python
'''
Total Questions: 741;
    Confirmation Questions: 122
    Factoid-type Questions: 114
    List-type Questions: 103
    Causal Questions: 105
    Hypothetical Questions: 111
    Complex Questions: 186;
        Generated using Dense Search for Similariy Search: 94
        Generated using Sparse Search for Similariy Search: 92
        Generated using Two Similar Chunks: 138
        Generated using Three Similar Chunks: 44
'''
```

We used three metrics that are mentioned above; BLEU Score, ROUGE Score, BERT Score.

Having a diverse set of questions, we come to a conclusion that the more context we have while generating references and predictions by different models, the more close references and predictions get to each other. 

In Confirmation Questions, we have the least amount of context given to the models, and interestingly we get the lowest scores for Confirmation Questions. 
In Complex Questions Generated using 3 Chunks, we have the most amount of context given to the models, and for these questions we have the highest scores.

We have better results for Complex Questions Generated using Dense Search than the ones generated using Sparse Search. This is because in our RAG Architecture, we use Dense Search to retrieve related chunks to generate a prediction. So, the references are generated using similar chunks by Dense Search as like predictions.

You can see the scores, and some details why these results are returned by the metrics, below;

#### BLEU Scores Test Set 1
In the chart given below, we have BLEU Score and 4 Precision Scores for different sets of questions.

<div style="text-align:center"><img src="images/BLUE-Scores.png" /></div>

As we can see from the chart, the BLEU scores are not satisfactory. There is a very good reason for these scores, that is different language models (gpt-3-5-turbo and Falcon-7B-Instruct) have varying vocabularies due to diverse training data, leading to differences in word choices for answers for questions. This discrepancy in vocabulary can result in lower BLEU scores when comparing translations from these models.  BLEU primarily focuses on precision, measuring how many of the generated n-grams appear in the reference (by gpt-3-5-turbo).

It doesn't account for differences in recall or consider synonyms effectively. If the models use different words for similar meanings, it can lead to lower BLEU scores despite conveying the intended answer. 

As an example, in Confirmation Questions, [`gpt-3.5-turbo-1106`](https://platform.openai.com/docs/models/gpt-3-5-turbo) mostly generates answers as either 'Yes' or 'No', but our model [`Falcon-7B-Instruct`](https://huggingface.co/tiiuae/falcon-7b-instruct) generates additional content. Even though the meaning of the answers are same. We got the lowest BLEU Score for Confirmation Questions as can be seen from the chart above.

#### ROUGE Scores Test Set 1
In the chart given below, we have 4 ROUGE Scores.

<div style="text-align:center"><img src="images/ROUGE-Scores.png" /></div>

As we can see ROUGE Scores are better than the BLEU Scores. This is because ROUGE prioritizes recall over precision, measuring what percent of n-grams in the reference occur in the generated output. As we mentioned previously, references usually contain less words, and since ROUGE is looking for reference words in the generated output, its scores are better than the BLEU scores.

It is important to mention that, the ROUGE Scores are still not good enough. This is again because of the vocabulary differences, the references and generated predictions may mean the same thing but have different word choices. As like BLEU, ROUGE does not campture the meaning of word and sentence semantics.

#### BERT Scores Test Set 1
In the chart given below, we have BERT Scores - F1, Precision, Recall.

<div style="text-align:center"><img src="images/BERT-Scores.png" /></div>

As we can see th BERT Scores are relly impressive with an F1 score for the full testing set being 0.87.
This is because of the fact that BERT Score utilizes contextualized embeddings to represent the tokens meaning unlike BLEU and ROUGE, it captures word and sentence semantics. BERT Score considers contextual information, allowing it to handle variations in word order and syntactic structures more effectively. Additionally, BERT models used to campute BERT Scores are trained on vast and diverse datasets, which results in a more comprehensive understanding of language.


## Test Dataset Generation Approach 1
Our goal was to generate a testing dataset that contain the following types of questions based on the given abstracts; 1) Yes/No Questions, 2) Factoid-type Questions [what, which, when, who, how], 3) List-type Questions, 4) Causal Questions [why or how], 5) Hypothetical Questions, 6) Complex Questions

### Question Generation Process:
We generate 100 for each Simple Question type: Confirmation, Factoid-type, List-type, Causal, Hypothetical and 100 for each Complex Question type: Complex Questions Generated by similar chunks found by Dense Search and Complex Questions Generated by similar chunks found by Sparse Search. 
While doing Sparse Search, 40 of 100 Complex Question Generations we use 1 keyword of the original chunk as the query to find similar chunks, another 40 of 100 we use 2 keywords as query, and the final 20 of 100 we use 3 keywords as our query. 
In both Dense and Sparse Searches, in the 75% of the searches we look for the most similar chunk, in the 25% of it we look for the two most similar chunks.

In the below diagram, you can see how we generate Complex Questions from each of our 100 chunks;

<div style="text-align:center"><img src="images/question-generations.png" /></div>

All these different ways of generating complex questions are for having more diverse set of questions and they are all explained in detail this section of Question Generation Process.

We use the available chunked abstracts of documents from pubmed dataset to generate an initial testing-set. [`test_dataset.csv`](data_preprocessing/qa_testing_data_generation/approach1/test_dataset.csv)

We make use of prompt engineering and free available api of OpenAI that uses the model [`gpt-3.5-turbo-1106`](https://platform.openai.com/docs/models/gpt-3-5-turbo) to generate questions and their answers from the given chunked abstract. We have also tried other freely available models but they do not offer enough rate for our case. Those models include but not limited to [`Llama 2`](https://huggingface.co/meta-llama), [`Falcon-7B-Instruct`](https://huggingface.co/tiiuae/falcon-7b-instruct). So, we had to continue with gpt-3.5-turbo model.
In order to generate a question and its answer pair, we need to have a prompt to send to gpt-3.5-turbo model and get its response.
#### Prompt Engineering
We create 6 prompts for each question type. The response to these prompts by the model should obey the rule of, question and answer both being inside of quotation marks as if they are strings and they should be returned as a list of 2 strings - ['questions', 'answer']. Having a prompt for each question type is especially useful to know/mark which type of question is generated. This is also beneficial in terms of making a prompt as specific as possible. 

##### Simple Questions: Confirmation, Factoid-type, List-type, Causal, Hypothetical
For questions; Confirmation, Factoid-type, List-type, Causal, Hypothetical, we use the following prompts for each question concatenated (as a list given below in the script, [`testing_set_generation.py`](data_preprocessing/qa_testing_data_generation/approach1/testing_set_generation.py)). Note: The final prompt for Complex questions in this list will also be used but not as the way the simple questions are used (more on this later).
```Python    
prompts = ["You to generate a Yes/No question that require an understanding of a given context and deciding a \
boolean value for an answer, e.g., 'Is Paris the capital of France?'. ",
            "You need to generate a Factoid-type Question [what, which, when, who, how]: These usually begin with a “wh”-word. \
An answer then is commonly short and formulated as a single sentence. e.g., 'What is the capital of France?'. ",
            "You need to generate a List-type Question: The answer is a list of items, e.g.,'Which cities have served as the \
capital of France throughout its history?'. ",
            "You need to generate a Causal Questions [why or how]: Causal questions seek reasons, explanations, and \
elaborations on particular objects or events, e.g., “Why did Paris become the capital of France?” \
Causal questions have descriptive answers that can range from a few sentences to whole paragraphs.",
            "You need to generate a Hypothetical Question: These questions describe a hypothetical scenario \
and usually start with “what would happen if”, e.g., 'What would happen if Paris airport closes for a day?'.",
            "You need to generate a Complex Question: Complex questions require multi-part reasoning by understanding \
the semantics of multiple text snippets, e.g. 'What cultural and historical factors contributed to the development of the \
Louvre Museum as a world-renowned art institution?' which requires inferring information from multiple documents to generate an answer."
]
```

Each time, one of this question type specific prompts is concatenated to common prompts and a chunk to generate the final prompt to be sent to the model and get a testing-set record. In the below code snippet in [`testing_set_generation.py`](data_preprocessing/qa_testing_data_generation/approach1/testing_set_generation.py), propmt[j] refers to a question type specific prompt given above and chunk refers to the chunk that we want to generate our question based on.

```Python
prompt = prompts[j] + "You need to use the given text snippet to generate the question!!. You also need to generate an answer for your question. \
The given text snippet is: " + chunk + " Remember and be careful: each of the entries in the lists should be a string with quotation marks!! " + "You \
just give a python list of size 2 with question and its answer for the given chunk at the end. That is like ['a question', 'an answer to that question']. \
IT IS SOO IMPORTANT TO GIVE ME A LIST OF 2 STRINGS THAT IS QUESTION AND ANSWER!!!"
```

##### Complex Questions:
For Complex questions, we have a few variations. First of all, in order to generate a complex question we need to find one or more similar chunks to the chunk that we have. We should do a similarity search and we use Dense or Sparse search to find similar chunks. In our case, we either look for the most similar chunk or the most two similar chunks.
###### Dense Search
We do Dense Search by taking the embedding of our chunk and looking for the chunks that have similar embeddings. In the below code snippet where we do the Dense Search, query_embedding_dense[0].tolist() is the embedding of our chunk and size is the number of similar chunks that we are looking for plus 1 (More on this later). 
```Python
search_query_dense = {    
    "query": {
        "knn": {
            "embedding": {
                "vector": query_embedding_dense[0].tolist(),
                "k": size
            }
        }
    }
}
```
###### Sparse Search
We do Sparse Search by taking 1 keyword, 2 keywords or 3 keywords as our query and looking for the chunks that has similar content. In the below code snippet that is used for Sparse Search, query_sparse is the query, and the size is again the number of similar chunks that we are looking for plus 1.

```Python
search_query_sparse = {
    "query": {
        "match": {
            "chunk": query_sparse
        }
        },
    "size": size
}
```

We look for one more of the number of chunks we need. That is because of the fact that sometimes the chunk itself may be returned as a similar chunk. So, we handle it by taking one more similar chunk, and if none of the similar chunks is the chunk itself, we take the first one or two similar chunks (depending on how many similar chunks we are looking for), if one of the similar chunks is the chunk itself, we take the other chunk(s). 

In the get_similar_chunks() function in[`testing_set_generation.py`](data_preprocessing/qa_testing_data_generation/approach1/testing_set_generation.py), we get the similar chunks and their properties, this is where we consider the case of similar chunk being the chunk itself using the below code snippet from the function;

```Python
if pmid_similar == pmid_original and chunk_id_similar == chunk_id_original: # if the found similar chunk is the chunk itself
    continue
```

So, by now, we have our similar chunks either from Dense Search or Sparse Search, and now we can create our prompt to be sent to our model for the generation of a Complex Question.

If we want to generate a Complex Question using 2 chunks (original chunk and its most similar) we use the following prompt where prompts[j] is the final prompt that explains what is a complex question, chunk is the original chunk, and chunk2 is its most similar chunk;

```Python
prompt = prompts[j] + "You need to use the given 2 different given text snippets to generate the question!!. You also need to generate an answer for your question. \
The first given text snippet is: " + chunk + " The second given text snippet is: " + chunk2 + " Remember and be careful: each of the entries in the lists should be a string with quotation marks!! " + "You \
just give a python list of size 2 with question and its answer for the given chunk at the end. That is like ['a question', 'an answer to that question']. \
IT IS SOO IMPORTANT TO GIVE ME A LIST OF 2 STRINGS THAT IS QUESTION AND ANSWER!!!"
```

If we want to generate a Complex Question using 3 chunks (original chunk and its two most similar chunks) we use the following prompt where prompts[j] is again one of the origianl prompts that explain Complex Question type, chunk is the original chunk, chunk2 is its most similar chunk, chunk3 is its second most similar chunk;

```Python
prompt = prompts[j] + "You need to use the given 3 different given text snippets to generate the question!!. You also need to generate an answer for your question. \
The first giventext snippet is: " + chunk + " The second given text snippet is: " + chunk2 + " The third given text snippet is: " + chunk3 + " Remember and be careful: each of the entries in the lists should be a string with quotation marks!! " + "You \
just give a python list of size 2 with question and its answer for the given chunk at the end. That is like ['a question', 'an answer to that question']. \
IT IS SOO IMPORTANT TO GIVE ME A LIST OF 2 STRINGS THAT IS QUESTION AND ANSWER!!!"
```

### Records to the Initial Test Set
By now, we have our prompt ready. We can now send it to the gpt-3-5-turbo model and get a question and its answer pair and we do this using the following code snippet;

```Python
def gpt_3_5_turbo(prompt):
    '''
    This function is used to send a prompt to gpt-3-5-turbo model to generate a question and its answer.
    '''
    time.sleep(30) # sleep each time before sending any prompt to gpt
    chat_completion = client_OpenAI.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        model="gpt-3.5-turbo-1106"
    )
    reply = chat_completion.choices[0].message.content
    return reply
```

The only remaining thing is to write the record to our initial testing set [`test_dataset.csv`](data_preprocessing/qa_testing_data_generation/approach1/test_dataset.csv). However, before writing it to this set we need to make sure that gpt-3-5-turbo model returned the pair in a valid format e.g. ['question', 'answer'], if not we need to convert it to the correct format and then write it. We do both checking the format of the model returned response and and then writing a record to the initial testing set using the  write_to_test_set() function in [`testing_set_generation.py`](data_preprocessing/qa_testing_data_generation/approach1/testing_set_generation.py). As explained in the function, we also keep track of the warnings in the cases of different invalid responses from the model and try to convert them to the correct format or drop them. 

#### Generating the Labeled Test Set
Now we have created an initial test predictions/labels [`test_dataset.csv`](data_preprocessing/qa_testing_data_generation/approach1/test_dataset.csv) that has questions, their answer, types and other attributes of the chunks used. However, it does not have predictions/answers by the model that our system is built on. 

So, we create a labeled test-set [`references_predictions.csv`](data_preprocessing/qa_evaluation/approach1/references_predictions.csv) from our initially generated test-set. We used our llm model [`Falcon-7B-Instruct`](https://huggingface.co/tiiuae/falcon-7b-instruct) to generate the predictions/labels for our questions in the original test-set. 
In the script; [`get_references_predictions.py`](data_preprocessing/qa_evaluation/approach1/get_references_predictions.py) we make calls to our frontend to get the prediction for our questions and then modify the prediction to remove sources as our references generated by [`gpt-3.5-turbo-1106`](https://platform.openai.com/docs/models/gpt-3-5-turbo) do not contain sources;
```Python
def get_prediction_from_llm(question):
    '''
    This function is used to get the prediction from our llm for the given question.
    We also modify it here - remove the sources as our references do not contain sources.
    '''
    url = f'http://localhost:8000/retrieve_documents_dense?query_str={question}'
    
    response = requests.get(url)

    if not response.ok:
        raise ValueError(f'HTTP error! Status: {response.status_code}')

    original_prediction = response.json()['message']
    return modify_original_prediciton(original_prediction)
```
So, by now, we have question, reference (answer by 'gpt-3-5-turbo'), prediction (answer by our model 'Falcon-7B-Instruct') and the question type for each of the questions that we have. 
We write these 4 attributes for each question to our final testing test [`references_predictions.csv`](data_preprocessing/qa_evaluation/approach1/references_predictions.csv) that we can use for evaluation.





## Test Dataset Generation Approach 2
    The [`gen_complex.py`](data_preprocessing\qa_testing_data_generation\approach2\gen_complex.py)script is designed to generate complex questions based on pairs of scientific abstracts with overlapping keywords. It utilizes the OpenAI GPT-3.5 API to create questions that require understanding the semantics of both abstracts. The process involves reading abstracts from a CSV file, identifying pairs with a significant number of common keywords, and then using these pairs to generate questions aimed at testing comprehension and reasoning abilities.

    Key Features:
    Safe Literal Evaluation: Safely evaluates strings to Python literals, ensuring that malformed strings are handled gracefully.
    Complex Question Generation: Leverages GPT-3.5 model to formulate complex questions that require multi-part reasoning, enhancing the depth of understanding required to answer.
    Pair Extraction Based on Keywords: Identifies abstract pairs with a substantial overlap in keywords, indicating potential thematic or semantic connections.

How It Works:
Reading Data: The script reads abstracts and their associated keywords from a specified CSV file.
Identifying Unique Pairs: It identifies unique pairs of abstracts with more than 15 common keywords, suggesting a meaningful connection between them.
Generating Questions: For each identified pair, the script generates a complex question by synthesizing the content of both abstracts.
Output: The generated questions and their corresponding abstract pairs are saved to an output CSV file for further use.

Usage:
Set your OpenAI API key in the script.
Specify the input CSV file path containing the abstracts and keywords.
Define the output CSV file path where the generated questions will be saved.
Run the script to produce a dataset of complex questions based on scientific abstracts.
The Test data set is then manually checked for any discrepancies using the open-source text annotation tool [`Doccano`](https://github.com/doccano/doccano)

    
