import pandas
import re, csv
from openai import OpenAI
import ast
import time

df = pandas.read_csv("data_preprocessing/data/exported_data.csv", usecols=['pmid', 'abstract'])

df_already_processed_documents_pmid = pandas.read_csv("data_preprocessing/test_data/test_dataset.csv", usecols=["PMID"], sep='\t')
already_processed_documents_pmid = set(df_already_processed_documents_pmid['PMID'])

# print(already_processed_documents_pmid)

client = OpenAI(
    api_key = "# TO BE INSERTED HERE"
)


count = 0
seen_documents_pmid = set()
question_types = ["Confirmation", "Factoid-type", "List-type", "Causal", "Hypothetical", "Complex"] # 6 types
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
"Complex Questions: PROMPT TO BE DETERMINED"
]

print(prompts)
for i in range(df.shape[0]):
    if count == 10:
        break
    pmid, abstract = df.iloc[i, ]
    if pmid not in seen_documents_pmid and pmid not in already_processed_documents_pmid:
        for i in range(5):
            time.sleep(30)
            seen_documents_pmid.add(pmid) # multiple columns contain the same abstract due to chunking
            question_type = question_types[i]
            prompt = prompts[i] + "You need to use the given abstract to generate the question!!. You also need to generate an answer for your question. \
The abstract is: " + abstract + " Remember and be careful: each of the entries in the lists should be a string with quotation marks!! " + "You \
just give a python list of size 2 with question and its answer for the given abstract at the end. That is like ['a question', 'an answer to that question']. \
IT IS SOO IMPORTANT TO GIVE ME A LIST OF 2 STRINGS THAT IS QUESTION AND ANSWER. IF YOU THING THAT THIS KIND OF QUESTION CANNOT BE GENERATED JUST TELL ME 'NA'.\
DO NOT HALLUSINATE!!!"
            # print(question_type)
            # print(prompt)
            if prompt:
                chat_completion = client.chat.completions.create(
                    messages=[
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    model="gpt-3.5-turbo-1106"
                )
            reply = chat_completion.choices[0].message.content
            if reply.lower == "na":
                continue
            # print(reply)
            try:
                # Check if ChatGPT gave the response in a correct format
                result_list = ast.literal_eval(reply)
                if isinstance(result_list, list) and all(isinstance(item, str) for item in result_list):
                    # everything is good, we can add this to our dataset
                    test_set_file_path = 'data/test_dataset.csv'

                    with open(test_set_file_path, 'a', newline='') as file:
                        csv_writer = csv.writer(file, delimiter='\t')
                        
                        # PMID1, PMID2, PMID3, CHUNK1, CHUNK2, CHUNK3, abstract, question_type, question, answer, keywords_if_complex
                        new_record = [pmid, "N/A", "N/A", "N/A", "N/A", "N/A", abstract, question_type] + result_list + ["N/A"]
                        csv_writer.writerow(new_record)
                else:
                    print("WARNING: NOT CORRECTLY GENERATED")
                    # print(reply)
                    continue
            except (SyntaxError, ValueError):
                print("WARNING: A LIST IS NOT GENERATED!")
                print(reply)
                continue
            # print(reply)
        count += 1


# Here we are taking sample of size 50, from which we can take the keywords
# for our keyword based similarity search on opensearch
df_data_embeddings = pandas.read_csv("data_preprocessing/data/data_embeddings_500_100.csv", usecols=['pmid', 'title', 'chunk_id', 'chunk', 'key_words'])

df_data_embeddings = df_data_embeddings[df_data_embeddings['key_words'].notna()] # data records with key_words

df_data_embeddings['key_words'] = df_data_embeddings['key_words'].apply(ast.literal_eval) # convert the key_words to list type


# After investigation of the data records, we observed
# that the more keywords a data record has the keywords are more generic
# and we also need to have dat records with at least 3 key_words for our similarity search
# so we decided on the size: minimum: 4 keywords and maximum: 6 keywords
df_data_embeddings = df_data_embeddings[df_data_embeddings['key_words'].apply(lambda x: isinstance(x, list) and len(x) >= 4 and len(x) <= 6)]


# Here we randomly take 50 data records to extract keywords
# for our similarity search based on keywords
sampled_data_records = df_data_embeddings.sample(n=50, random_state=42)

# Here we randomly take 20 records from 50 selected
# the first keyword of these 20 records will be used for similarity search with 1 keyword
one_keyword_search = sampled_data_records.sample(n=20, random_state=42)

# Dropping 20 records (for one keyword search) from the original 50 selected records
sampled_data_records = sampled_data_records.drop(one_keyword_search.index)

# Here we randomly take another 20 records from the remaining 30 initially selected records
# for our similarity search with 2 keywords
two_keywords_search = sampled_data_records.sample(n=20, random_state=42)

# Dropping another 20 records (for two keyword search) from the remaining 30 records
# and getting the final 10 records which will be used for similarity search with 3 keywords
three_keywords_search = sampled_data_records.drop(two_keywords_search.index)

# Now we have 3 dataframes with the sizes of 20, 20, 10 respectively
# Now we can take the keywords from these dataframes for our keyword based similariy search

# We keep only one keyword of the presented keywords (1st one) 
# from the first dataframe for our similarity search with one keyword
print(one_keyword_search['key_words'].head)

