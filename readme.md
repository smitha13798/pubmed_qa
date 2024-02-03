
### A RAG-based system for Pubmed

### Evaluation Metrics

Let's have an example to better understand the below mentioned evaluation metrics.
Text generated by the model = "Students enjoy doing NLP homeworks"
Reference text = "Students love doing homeworks"

- ROUGE (Recall-Oriented Understudy for Gisting Evaluation)
    ROUGE-N compares n-grams of the generated text by the model with n-grams of the reference text. N-grams is basically a chunk of n words. ROUGE measues what percent of the words or n-grams in the reference text occur in the generated output. 

    ROUGE-1 measures the overlap of unigrams (individual words) between the generated text and the reference text. 
    ROUGE-1 (recall) is number of matching words / number of words in reference. In our example ROUGE-1 (recall) is 3/4. Because 3 of the words in the generated text appeared in the reference text, that are "Students", "doing", "homeworks". The number of words in the reference text is 4. 
    ROUGE-1 (precision) is number of matching words / number of words in generated text. In our example, that is 3/5. Again we 3 word mathces, but this time we divide it by the number of words in the generated text, that is 5. 
    ROUGE-1 (F1-score) = 2 * ((precision * recall) / (precision + recall)). That is 0.66666666666. 

    ROUGE-2 measures 
