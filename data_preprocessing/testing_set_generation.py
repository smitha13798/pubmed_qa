import pandas
import re, csv
from openai import OpenAI
import ast
import time

# To create the test set csv file - run only once
'''
with open("data_preprocessing/test_data/test_dataset.csv", 'w', newline='') as file:
    # Create a CSV writer object with tab as the delimiter
    csv_writer = csv.writer(file, delimiter='\t')  # Specify tab as the delimiter

    header = ["pmid1", "pmid2", "pmid3", "chunk_id1", "chunk_id2", "chunk_id3", "abstract", 
    "question_type", "question", "answer", "keywords_if_complex"]
    csv_writer.writerow(header)
'''

# Here we store the chunks that we have already processed, in order not to use in the future
df_already_processed_documents = pandas.read_csv("data_preprocessing/test_data/test_dataset.csv", usecols=["pmid1", "chunk_id1"], sep='\t')
already_processed_documents= set(df_already_processed_documents['pmid1'] + '_' + df_already_processed_documents['chunk_id1'])

# # print(already_processed_documents)

# Here we are taking sample of size 50 to generate questions
# ?? from which we can take the keywords for our keyword based similarity search on opensearch
df_data_embeddings = pandas.read_csv("data_preprocessing/data/data_embeddings_500_100.csv", usecols=['pmid', 'title', 'chunk_id', 'chunk', 'embedding', 'key_words'])

# Here we need to keep the data records with keywords because we need the keywords
# for our similarity search - to find related documents to generate complex questions
df_data_embeddings = df_data_embeddings[df_data_embeddings['key_words'].notna()] # data records with key_words

df_data_embeddings['key_words'] = df_data_embeddings['key_words'].apply(ast.literal_eval) # convert the key_words to list type

# After investigation of the data records, we observed
# that the more keywords a data record has, more generic keywords are
# and we also need to have date records with at least 3 key_words for our similarity search
# so we decided on the size: minimum: 4 keywords and maximum: 6 keywords
df_data_embeddings = df_data_embeddings[df_data_embeddings['key_words'].apply(lambda x: isinstance(x, list) and len(x) >= 4 and len(x) <= 6)]


# Here we randomly take 100 data records to generate questions
# ??? to extract keywords for our similarity search based on keywords
sampled_data_records = df_data_embeddings.sample(n=100, random_state=42)


# Here we randomly take 40 records from 100 selected
# With these 40 chunks, only one keyword will be used to find similar chunks
# and eventually to generate a complex question
one_keyword_records = sampled_data_records.sample(n=40, random_state=42)

# Dropping 40 records (that uses one keyword for similarity) from the original 100 selected records.
sampled_data_records = sampled_data_records.drop(one_keyword_records.index)

# Here we randomly take another 40 records from the remaining 60, initially selected records.
# these chunks/records will use 2 keywords to find similar chunks to generate complex questions
two_keywords_records = sampled_data_records.sample(n=40, random_state=42)

# Dropping the records that will use 2 keywords for similariy search
# and getting the final 20 records which will use 3 keywords to find related chunks/records for complex question generation
three_keywords_records = sampled_data_records.drop(two_keywords_records.index)


# Now we have 3 dataframes with the sizes of 40, 40, 20 respectively
# Now we can generate the questions and do the complex question generation differently
# depending on the dataframe that our record/chunk belongs to

# 30 of 40 chunks that uses one keyword to find related chunks
# will be compined with one another chunk that is the most similar to it for complex question generation
# the oter 10 chunks will be compined with 2 other chunks that are the most similar to it for complex question generation
count_for_one_keyword_two_chunks = 0 # 30

# again 30 of 40 chunks that use two keywords to find related chunks
# will be compined with one another chunk, and 10 chunks will be combined with 2 other most similar chunks
# for complex question generation
count_for_two_keywords_two_chunks = 0 # 30

# 15 of 20 chunks that use three keywords to find related chunks
# will be compined with one another chunk, and 5 chunks will be combined with 2 other most similar chunks
count_for_three_keywords_two_chunks = 0 # 15


# client = OpenAI(
#     api_key = "# TO BE INSERTED HERE"
# )

question_types = ["Confirmation", "Factoid-type", "List-type", "Causal", "Hypothetical", 
                  "ComplexWithTwoChunks", "ComplexWithThreeChunks"] # 6 + 1 types


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
the semantics of multiple text snippets, 'What cultural and historical factors contributed to the development of the \
Louvre Museum as a world-renowned art institution?' which requires inferring information from multiple documents to generate an answer."
]

# print(prompts)

# Here I concatenate all the data records but we know that 
# first we have chunks that we will use one keyword to find its similar chunks,
# then we have records that we will use two keywords to find its similar chunks,
# and finally we have records that we will use three keywords to find its similar chunks.
# Rows of these records are stacked on top of the other.
all_records = pandas.concat([one_keyword_records, two_keywords_records, three_keywords_records], ignore_index=True)

count = 0
num_of_records = all_records.shape[0] # the number of samples we took 
for i in range(num_of_records):
    if count == 10:
        break
    pmid, title, chunk_id, chunk, embedding, key_words = all_records.iloc[i, ]

    # checking if we have already processed this chunk
    chunk_identifier = pmid + '_' + chunk_id
    if chunk_identifier not in  already_processed_documents:
        for j in range(6):
            time.sleep(30)
            question_type = question_types[i]

            # COMPLEX QUESTIONS
            if j == 5: # Complex question
                # Here we find how many keywords we need to use to find similar chunks
                # and also get the keywords to be used
                
                # After finding the keywords to be used
                # we also find the number of the most similar chunks we are looking for

                # ONE KEYWORD SEARCH
                if i < len(one_keyword_records): # we are still not done with one keyword seaches
                    # one keywrod search
                    keywords = key_words[0]
                    if count_for_one_keyword_two_chunks < 30: 
                        # we have to find only the most similar chunks
                        # because we agreed on finding one similar chunk for 30 of 40 records
                        num_of_similar_chunks = 1
                        count_for_one_keyword_two_chunks += 1
                    else:
                        # otherwise we find two most similar chunks
                        num_of_similar_chunks = 2

                # TWO KEYWORDS SEARCH
                elif i < len(one_keyword_records) + len(two_keywords_records): # we are still not done with two keywords searches
                    # two keywords search
                    keywords = key_words[0] + key_words[1]
                    if count_for_two_keywords_two_chunks < 30: 
                        # we have to find only the most similar chunks
                        # because we agreed on finding one similar chunk for 30 of 40 records
                        num_of_similar_chunks = 1
                    else:
                        num_of_similar_chunks = 2

                # THREE KEYWORDS SEARCH
                else:
                    # three keywords search
                    keywords = key_words[0] + key_words[1] + key_words[2]
                    if count_for_three_keywords_two_chunks < 15:
                        # we have to find only the most similar chunks
                        # because we agreed on finding one similar chunk for 15 of 20 records
                        num_of_similar_chunks = 1
                    else:
                        num_of_similar_chunks = 2
                
                # NOW WE HAVE EVERYTHING TO FIND THE MOST SIMILAR CHUNK(S)
                # WE HAVE THE KEYWORDS AND WE HAVE SIZE OF OUR SEARCH, MEANING HOW MANY SIMILAR CHUNKS ARE WE INTERESTED IN
                
                # keywords
                # num_of_similar_chunks
                
                # WE NEED TO EXTRACT THE CHUNKS HERE
                similar_chunks = [...]        
                chunk2 = similar_chunks[0]['chunk']
                
                if num_of_similar_chunks == 2:
                    chunk3 = similar_chunks[1]['chunk']

                # ONE SIMILAR CHUNK
                if num_of_similar_chunks == 1:
                    prompt = prompts[j] + "You need to use the given 2 different text snippets to generate the question!!. You also need to generate an answer for your question. \
The first text snippet is: " + chunk + " The second text snippet is: " + chunk2 + " Remember and be careful: each of the entries in the lists should be a string with quotation marks!! " + "You \
just give a python list of size 2 with question and its answer for the given chunk at the end. That is like ['a question', 'an answer to that question']. \
IT IS SOO IMPORTANT TO GIVE ME A LIST OF 2 STRINGS THAT IS QUESTION AND ANSWER. IF YOU THING THAT THIS KIND OF QUESTION CANNOT BE GENERATED JUST TELL ME 'NA'.\
IF YOU ALSO THING THAT GENERATING A QUESTION FROM THESE 2 GIVEN TEXT SNIPPETS DOES NOT MAKE SENSE JUST TELL ME 'NA' AGAIN!! DO NOT HALLUSINATE!!!"

                # TWO SIMILAR CHUNKS
                elif num_of_similar_chunks == 2:
                    prompt = prompts[j] + "You need to use the given 3 different text snippets to generate the question!!. You also need to generate an answer for your question. \
The first text snippet is: " + chunk + " The second text snippet is: " + chunk2 + " The third text snippet is: " + chunk3 + " Remember and be careful: each of the entries in the lists should be a string with quotation marks!! " + "You \
just give a python list of size 2 with question and its answer for the given chunk at the end. That is like ['a question', 'an answer to that question']. \
IT IS SOO IMPORTANT TO GIVE ME A LIST OF 2 STRINGS THAT IS QUESTION AND ANSWER. IF YOU THING THAT THIS KIND OF QUESTION CANNOT BE GENERATED JUST TELL ME 'NA'.\
IF YOU ALSO THING THAT GENERATING A QUESTION FROM THESE 2 GIVEN TEXT SNIPPETS DOES NOT MAKE SENSE JUST TELL ME 'NA' AGAIN!! DO NOT HALLUSINATE!!!"
            else:
                prompt = prompts[j] + "You need to use the given chunk of text to generate the question!!. You also need to generate an answer for your question. \
The text snippet is: " + chunk + " Remember and be careful: each of the entries in the lists should be a string with quotation marks!! " + "You \
just give a python list of size 2 with question and its answer for the given chunk at the end. That is like ['a question', 'an answer to that question']. \
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
#             # print(reply)
            try:
                # Check if ChatGPT gave the response in a correct format
                result_list = ast.literal_eval(reply)
                if isinstance(result_list, list) and all(isinstance(item, str) for item in result_list):
                    # everything is good, we can add this to our dataset
                    test_set_file_path = 'data_preprocessing/test_data/test_dataset.csv'

                    with open(test_set_file_path, 'a', newline='') as file:
                        csv_writer = csv.writer(file, delimiter='\t')
                        
                        # PMID1, PMID2, PMID3, CHUNK_ID1, CHUNK_ID2, CHUNK_ID3, chunk, question_type, question, answer, keywords_if_complex

                        # 2 CHUNKS USED FOR COMPLEX QUESTION GENERATION
                        if j == 5 and num_of_similar_chunks == 1:
                            new_record = [pmid, pmid2, "N/A", chunk_id, chunk_id2, "N/A", chunk, question_type] + result_list + [key_words]

                        if j == 5 and num_of_similar_chunks == 2:
                            new_record = [pmid, pmid2, pmid3, chunk_id, chunk_id2, chunk_id3, chunk, question_type] + result_list + [key_words]

                        #NORMAL QUESTIONS
                        else:
                            new_record = [pmid, "N/A", "N/A", chunk_id, "N/A", "N/A", chunk, question_type] + result_list + ["N/A"]

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


# # We keep only one keyword of the presented keywords (1st one) 
# # from the first dataframe for our similarity search with one keyword
# print(one_keyword_search['key_words'].head)