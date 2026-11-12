import streamlit as st
from PyPDF2 import PdfReader
from langchain.text_splitter import RecursiveCharacterTextSplitter
import os
import openai
from openai import OpenAI
from langchain_openai import OpenAIEmbeddings
from langchain_openai import AzureOpenAIEmbeddings
from langchain_openai import ChatOpenAI
import google.generativeai as genai
from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import UnstructuredPowerPointLoader
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.chains.retrieval import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.prompts import PromptTemplate
from langchain.docstore.document import Document
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv

import tiktoken
import pdfplumber


load_dotenv()

OPENAI_API_KEY =os.getenv("OPENAI_API_KEY")

def save_docs_to_txt(docs, filename):
    os.makedirs(os.path.dirname(filename), exist_ok=True) if os.path.dirname(filename) else None
    with open(filename, "w", encoding="utf-8") as f:
        for doc in docs:
            # f.write(f"Source: {doc.metadata.get('source', 'Unknown')}, Page: {doc.metadata.get('page', 'Unknown')}\n")
            f.write(doc.page_content)
            # f.write("\n\n" + "="*100 + "\n\n")

def get_ppt_text_old(ppt_docs):
    docs1=[]
    for ppt in ppt_docs:
        if(ppt.name[-3:]=='pdf'):
            reader = PdfReader(ppt)
            i=1
            for page in reader.pages:
                docs1.append(Document(page_content=page.extract_text(), metadata={'source':ppt.name,'page':i}))
                i += 1
    return  docs1


def get_ppt_text(ppt_docs):
    docs = []
    for ppt in ppt_docs:
        # Only process PDFs
        if ppt.name.lower().endswith('pdf'):
            # Open the uploaded file (ppt is a file-like object)
            with pdfplumber.open(ppt) as pdf:
                for i, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text()
                    if text:
                        # pdfplumber returns text as lines separated by \n
                        # To closely match the output of your previous code:
                        docs.append(Document(
                            page_content=text,
                            metadata={'source': ppt.name, 'page': i}
                        ))
    return docs



def get_text_chunks(text):
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks = text_splitter.split_documents(text)
    return chunks


def get_vector_store(text_chunks):
    # Initialize embeddings and tokenizer
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small", openai_api_key=OPENAI_API_KEY)
    enc = tiktoken.encoding_for_model("text-embedding-3-small")
    
    MAX_TOKENS = max_tokens
    current_batch = []
    current_tokens = 0
    all_vectors = []

    for chunk in text_chunks:
        chunk_tokens = len(enc.encode(chunk.page_content))
        
        # If adding this chunk exceeds max tokens, embed current batch and start new one
        if current_tokens + chunk_tokens > MAX_TOKENS:
            if current_batch:
                faiss_partial = FAISS.from_documents(current_batch, embedding=embeddings)
                all_vectors.append(faiss_partial)
            current_batch = [chunk]
            current_tokens = chunk_tokens
        else:
            current_batch.append(chunk)
            current_tokens += chunk_tokens

    # Embed the final batch
    if current_batch:
        faiss_partial = FAISS.from_documents(current_batch, embedding=embeddings)
        all_vectors.append(faiss_partial)

    # Merge all FAISS indices
    final_vector_store = all_vectors[0]
    for partial_store in all_vectors[1:]:
        final_vector_store.merge_from(partial_store)

    # Save final FAISS index
    final_vector_store.save_local("faiss_index_job")
    st.write(final_vector_store.index.ntotal)


def get_conversational_chain():

    # prompt = ChatPromptTemplate.from_template("""
    # Answer the following question based only on the provided context. 
    # if the answer is not in provided context just say, "answer is not available in the context",
    # You are a sales assistant. 
    # Think step by step before providing an answer, make sure to provide all the details,
    # Please provide data in tabular form wherever possible, i.e. doing comparision. \n\n
    # <context>
    # {context}
    # </context>
    # Question: {input}""")

    # if the answer is not in provided context just say, "answer is not available in the context",
    # (also given below under <context>)
    #If the two conditions in final instruction 1 did not satisfy, do this as well :

    # 4. Finally, try and change individual points under both sets of "Highlight Projects" (2 points max in total) by changing the point to entirely new project points that I could have done given my resume and context provided, that are best suited for the job role, which can replace the same project points that are being changed in final instruction 1 (follow the same layout as final instruction 2 but display these suggestions in a new table).
    #      When describing these projects, do not be vague. List out specific tools, modules and methodologies (prefer using specific modules and methodologies over programming languages and common softwares) I could have used to solve a specific use case in the project description and make sure that the project name is technically sound to be put in a resume. 
    #      Ensure that the modified version of each project point has the same number or lesser number of characters than that of the original project point. If lesser, ensure that it is no
    #                         lesser than 3.\n  

    if st.session_state.ch == 0:

        prompt = ChatPromptTemplate.from_template("""                                                                                  
        IMPORTANT INSTRUCTIONS ON HOW THIS PROMPT MUST BE READ : Read this prompt from top to bottom and follow the instructions as given from top to bottom, one after another.\n\n 
        MOST IMPORTANT (REMEMBER) : The below provided resume comes to exactly 2 pages in google docs so whatever modifications are made as per my request
        in later parts of this prompt, please make sure that the modified version of any line or paragraph comes to about the same, 
        number of characters than that of the original. Also, Answer the following question based only on the provided context (unless specified otherwise).
        If the answer is not in provided context just say, "Answer is not available in the provided context" \n \n\n\n
        When answering, attempt to copy the style of english as given in english_style, while being gramatically correct, so that the responses feel like they are actually written
                                                 by me and not by an AI to a job recruiter.
        \n\n
        english_style :
        <english_style>
        {english_style}
        </english_style>
        \n\n 
        Resume :
        <resume>
        {resume}
        </resume>
        \n\n 
        Overall instructions :    
        Using the resume provided above, tailor each section to the job description (provided below) based only on the provided context (important) (also given below),
        and the instructions provided for each section, hence increasing my chances in attaining an interview. If there is a modification 
        that makes my resume more tailored for the job role, but does not lie in the context provided, do not commit to that change.
          \n\n
        Instructions :\n
        1. For the Summary section of my resume, only attempt to modify the skills listed under "Other expertise includes -" in the last line
        of the summary unless there is hardly any/very less correlation between the rest of my Summary and the job description. In this case,
        you may attempt to change one or two lines to suit the job description. \n

        2. In the skills and areas of interest section, do not ever attempt to modilfy the first 5 skills (that is : 
        Python, R, Java, C++, Pytorch, Tensorflow). You may swap out the rest of the skills for skills that are closer to the job requirements
                                                  (as long as they are found in the context),
                                                  while removing the skills that are least necessary for the job role.\n
        3. For the areas of interest,  do not attempt to modify AI-Based Market Analysis and Augmented-Analytics. 
        You may swap out the rest of the areas of interest for areas of interest that are closer to the job requirements while removing the areas of interest that are least necessary for the job role.
        You can even add one area of interest that is not found in the context as long as it is heavily reliant in my job role as these are only "areas of interest"
        which are areas that i do not need to necessarily have knowledge/experience working in. (only exception to the important context rule mentioned above). \n
        
        4. While carrying out instructions 2 and 3, make sure that the modified skills and areas of interest consist of the same or lesser characters
        than the skills and areas of interest of the original resume. If the modified version has lesser characters, ensure that it is no lesser than 3 characters.\n
        5. If swapping out a current certification for a certification/achievement from the provided context increases my chances
        of landing an interview by atleast 15%, then do it by removing the certification that is least relevant. \n
        6. Now, check for these 2 conditions :
                                                  1. More than than 90 percent of the skills mentioned in the job description are present in my modified resume.
                                                  2. The skills required in the job description encompass atleast 75 percent of my modified resume. \n
        If either of these two conditions do not satisfy, store string S = "Project Modifications Recommended. (Then say which condition(s) did not satisfy)", else, store string S = "Project Modifications Unnecessary."\n
        
        7. (Important) Irrespective of what string S is from the previous instruction, analyze the individual points under both sets of "Highlight Projects" and notice which points have the least relevance with the job description. Now modify these points (3 maximum) by changing the point to
        highlight more job related skills while maintaining similar meaning or by swapping out less
        relevant projects with respect to the job description for more relevant ones from other resumes in the provided context, whichever would increase my chances more for landing an interview for the job role.(If the first option is the chosen way for modifying a point, make sure to not change the project title). Once again,
        ensure that the modified version of each point has the same number or lesser number of characters than that of the original point. If lesser, ensure that it is no
                            lesser than 3.\n\n

        Final Instructions :\n

        1. Display the output in a tabular format (Section Name | Old version | New version) which only shows the individual lines/words that were modified in each section (provide
        the section name for easy referencing). Make sure that all suggested changes comply with the character rule given at the start and make sure the suggested changes are given
        in full such that it can be immediately copied and pasted into my resume. Display string S after the table (just the string. without the S: or S = etc.).\n
        
        2. Summarize the job role (what I am required to do) into one sentence and Key skills and display them in this format :
        Company name : (Put the company name here) \n
        Job role : (Put the job title as mentioned in the job description) \n
        Summarized Duty : (Put the one sentence that you previously summarized) \n
        Key Skills : (List out the key skills required for the job like this : AWS, Excel, Python....) \n\n
                                        
        Display this above the output displayed from final instruction number 1 (the table)   \n\n
                                                  
        3. Finally, suggest two entirely new project points that I could have done given my resume and context provided, that are best suited for the job role. These must follow the same structure as the points under "Highlight Projects" from my resume.
         When describing these projects, do not be vague. List out specific tools, modules and methodologies (prefer using specific modules and methodologies over programming languages and common softwares) I could have used to solve a specific use case in the project description and make sure that the project name is technically sound to be put in a resume. 
         Ensure that the number of characters used in each project point are similar to that of the points under "Highlight Projects" from my resume.\n  
                                       
                                                  
                                                  \n\n
        Context :
        <context>
        {context}
        </context>\n\n
        Job Description : {input}
        """)

    # as long as it lies within the context provided.
    # If the answer is not in provided context just say, "Answer is not available in the context".

    elif st.session_state.ch == 1:
        prompt = ChatPromptTemplate.from_template("""
        With my current resume and within only the scope of the context given below (important), answer for me the job application question given at the end while keeping in mind the given job description.
                                                  
        When answering, attempt to copy the style of english as given in english_style, while being gramatically correct, so that the responses feel like they are actually written
                                                 by me and not by an AI to a job recruiter.                                  
        Feel free to add some creativity and additional details as well in the answers if necessary to help with its ebb and flow,
        as long as it is realistically possible and believeable from the POV of a job recruiter.\n\n
        Job Description :
        <job_desc>
        {job_desc}
        </job_desc>
        \n\n 
        english_style :
        <english_style>
        {english_style}
        </english_style>
        \n\n 
        Resume :
        <resume>
        {resume}
        </resume>
        \n\n 
        Context:
        <context>
        {context}
        </context>\n\n
        Question: {input}\n\n
        {extra}""")
    
    elif st.session_state.ch == 2:

        prompt = ChatPromptTemplate.from_template("""
        MOST IMPORTANT (REMEMBER) : The below provided cover letter comes to exactly 0.75 pages in google docs so whatever modifications are made as per my request
        in later parts of this prompt, please make sure that the modified version of the whole cover letter comes to approximately 1 page. Also, Answer the following question based only on the provided context (unless specified otherwise).
        If the answer is not in provided context just say, "Answer is not available in the provided context" \n \n\n\n
        When answering, attempt to copy the style of english as given in english_style, while being gramatically correct, so that the responses feel like they are actually written
                                                 by me and not by an AI to a job recruiter. On that note, feel free to add some creativity and additional details as well in the answers if necessary to help with its ebb and flow,
        as long as it is realistically possible and believeable from the POV of a job recruiter.
        \n\n
        english_style :
        <english_style>
        {english_style}
        </english_style>
        \n\n 
        Resume :
        <resume>
        {resume}
        </resume>
        \n\n 
        Cover Letter :
        <cl>
        {cl}
        </cl>
        \n\n 
        Overall instructions :    
        Using the cover letter provided above, tailor each section to the job description (provided below) based only on the provided context (important) (also given below),
        my latest resume (also provided above), and the instructions provided for each section, hence increasing my chances in attaining an interview.
        Do not copy any line from my resume word for word onto the cover letter. If absolutely necessary, paraphrase. If there is a modification 
        that makes my cover letter more tailored for the job role, but does not lie in the context provided, do not commit to that change.
          \n\n
        Instructions :
        1. Take a note on the structure of the cover letter. I want the modified cover letter to also follow this format. It is divided
        into 4 sections, namely, the introduction (greetings and 1st paragraph), a little bit about me and my skillset (2nd and 3rd paragraphs),
        the reasons as to why i am a good fit (written in bullet points) (the 4th paragraph), and the conclusion (5th paragraph and ending).\n

        2. Modify the 1st section expressing a sense of thrill/excitedness for being able to potentially be a part of the company.
                                                  
        State my key skill and what is best about me that i can bring to the table for my job role. Make this section 1.5 times bigger than what it is 
        in the provided cover letter.\n
                                                  
        3. The second section must consist of my key experiences that tie in well with the job role, either from my experience or education. My previous work
        experiences and my Msc dissertation are my key talking points so do prioritize them in this section if relevant to the job role.
         If relevant, slip in a certification as well. Make this section also 1.5 times as long as than what it is the provided cover letter.\n
                                                  
        4. The 3rd section is the most important section as it must have points regarding why I am a standout candidate. Make sure to
        not repeat points from previous sections here. Save the best points to be put here. Follow the same bullet point structure.
        Do not exceed more than 5 bullet points or go below 3 bullet points.\n
                                                  
        5. The 4th and final section is the conclusion in which the most freedom can be taken in expressing thanks for considering my
        application and anything else that is relevant/specific questions from the job description can be addressed here. \n\n

        Final Instructions :
        1. After completing the above instructions, check for these 2 conditions :
                                                  1. More than than 90 percent of the skills mentioned in the job description are present in my modified cover letter.
                                                  2. The skills required in the job description encompass atleast 85 percent of my modified cover letter. \n
        If either of these two conditions do not satisfy, tell me which of the 2 do not satisfy and try to modify section 2 by changing lines
        to make it more closely related with the job description as long as they are in the provided context.  \n

        2. Fitch Ratings is the name of a company. Change this name to the company name from the job description wherever necessary. \n

        3. Display the modified cover letter from greetings to regards with the correct paragraph spacing, making sure to follow the format 
        of the original while increasing it from a 0.75 page cover letter to a 1 page cover letter (as requested earlier).\n
        
        4. Finally, summarize the job role (what I am required to do) into one sentence and Key skills and display them in this format :
        Company name : (Put the company name here) \n
        Job role : (Put the job title as mentioned in the job description) \n
        Summarized Duty : (Put the one sentence that you previously summarized) \n
        Key Skills : (List out the key skills required for the job like this : AWS, Excel, Python....) \n\n
                                        
        Display this above the output displayed from final instruction number 3 (the modified cover letter)                                                                               
                                                                                            
                                                  
                                                  
                                                  \n\n
        Context :
        <context>
        {context}
        </context>\n\n
        Job Description : {input}""")
    
    if st.session_state.ch == 1 or st.session_state.ch == 2:
        temperature = temperature1
    elif st.session_state.ch == 0 :
        temperature = temperature0


    model = ChatOpenAI(model=Model, temperature=temperature, api_key = OPENAI_API_KEY)

    chain=create_stuff_documents_chain(model,prompt)

    return chain



def user_input(user_question):
    # Use OpenAI's text-embedding-3-small (or large if needed)
    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=OPENAI_API_KEY  # Ensure this is set securely
    )

    # Load local FAISS vector store using OpenAI embeddings
    new_db = FAISS.load_local("faiss_index_job", embeddings, allow_dangerous_deserialization=True)

    if st.session_state.ch == 0 or st.session_state.ch == 2:
        score_threshold = score_threshold0
    elif st.session_state.ch == 1 :
        score_threshold = score_threshold1

    # Set up the retriever
    retriever = new_db.as_retriever(
        search_type="similarity_score_threshold",
        search_kwargs={
            "score_threshold": score_threshold,
            "k": k
        }
    )

    # Get the LLM chain
    chain = get_conversational_chain()

    # Create a retrieval chain
    retrieval_chain = create_retrieval_chain(retriever, chain)

    if st.session_state.ola:
        extra = "Important : Answer the question within a single sentence."
    else:
        extra = ""

    # Get the response from the chain
    response = retrieval_chain.invoke({"input": user_question,"resume": st.session_state.resume_text,"english_style":st.session_state.english_style,
                                       "job_desc":st.session_state.job_desc,"extra":extra,"cl":st.session_state.cl_text})

    # Display the answer
    st.write(response["answer"])

    # Extract and display source PDF information
    source_pdf = set()
    for context in response["context"]:
        source_pdf.add(context.metadata["source"])

    st.write("**Source PDFs**")
    for src in source_pdf:
        st.write(src)


#Global variables : (Change these as necessary)
max_tokens = 300_000
score_threshold0 = 0.25 #0 is for Resume_tailoring (also goes for 2 (Cover letter tailoring))
score_threshold1 = 0.2  #1 is for Q & A
k = 10
chunk_size=514*2 
chunk_overlap=76
temperature0 = 0.3 #0 is for Resume_tailoring
temperature1 = 0.425 #1 is for Q & A (also goes for 2 (Cover letter tailoring))
Model = "gpt-4o"


def main():
    st.set_page_config("Job Finder Bot")
    st.header("Job Finder Bot")


    if "ch" not in st.session_state:
        st.session_state.ch = 0
    if "ola" not in st.session_state:
        st.session_state.ola = False
    if "job_desc" not in st.session_state:
        st.session_state.job_desc = ""
    if "resume_text" not in st.session_state:
        if os.path.exists("Job Text Files/resume_text.txt"):
            with open("Job Text Files/resume_text.txt", "r", encoding="utf-8") as file:
                st.session_state.resume_text = file.read()
        else:
            st.session_state.resume_text = None
    if "cl_text" not in st.session_state:
        if os.path.exists("Job Text Files/cl_text.txt"):
            with open("Job Text Files/cl_text.txt", "r", encoding="utf-8") as file:
                st.session_state.cl_text = file.read()
        else:
            st.session_state.cl_text = None
    if "english_style" not in st.session_state:
        if os.path.exists("Job Text Files/english_style.txt"):
            with open("Job Text Files/english_style.txt", "r", encoding="utf-8") as file:
                st.session_state.english_style = file.read()
        else:
            st.session_state.english_style = None

    #Checking :

    # st.write(st.session_state.ch)
    # if st.session_state.job_desc is not None:
    #     st.write(st.session_state.job_desc)
    # else:
    #     st.write("None")
    # if st.session_state.resume_text is not None:
    #     st.write("Exists")
    # else:
    #     st.write("None")
    # if st.session_state.english_style is not None:
    #     st.write("Exists")
    # else:
    #     st.write("None")
    # st.write(st.session_state.ola)

    persona = st.radio(
    "***Contact Persona***",
    ["Tailor Resume","Tailor Cover Letter","Q and A"],
    horizontal=True)
    persona_text=""

    if persona =="Tailor Resume":
        st.session_state.ch = 0
        persona_text = ""
    elif persona =="Q and A":
        st.session_state.ch = 1
        persona_text = ""
    elif persona =="Tailor Cover Letter":
        st.session_state.ch = 2
        persona_text = ""
    
    # st.subheader("Enter your question here")
    st.text_area("Enter the job description...",key = "job_desc",height=150)
    if st.session_state.ch == 0:
        user_question = ""
    elif st.session_state.ch == 1:
        user_question = st.text_area("What do you wanna know?",height=75) #,key = "ch1area"
    # user_question = st.text_area(" ")
        st.toggle("One Line Answer",key = "ola")
    elif st.session_state.ch == 2:
        user_question = ""

    
    st.button("Ask",key="ask_button")
    if st.session_state.ask_button and st.session_state.job_desc != "" and os.path.exists("faiss_index_job/index.faiss"):
        if st.session_state.ch == 0 or st.session_state.ch == 2:
            user_question = st.session_state.job_desc

        user_input(user_question+". "+ persona_text)
    elif st.session_state.ask_button and st.session_state.job_desc == "":
        st.write("No job description provided")
    elif st.session_state.ask_button and not os.path.exists("faiss_index_job/index.faiss"):
        st.write("No context files provided \n\n Provide context files for personalized results...\n\n\n\n")
        user_input(user_question+". "+ persona_text)

    with st.sidebar:

        st.title("Add your Resume:")
        ppt_docs = st.file_uploader("Upload your PDF Files and Click on the Submit & Process Button", accept_multiple_files=True,key = "resumeuploader")
        if st.button("Submit & Process",key = "RESUME"):
            with st.spinner("Processing..."):
                raw_text2 = get_ppt_text(ppt_docs)
                # st.write(raw_text2)
                save_docs_to_txt(raw_text2,"Job Text Files/resume_text.txt")
                st.success("Done")

        st.title("Add your Cover Letter:")
        ppt_docs = st.file_uploader("Upload your PDF Files and Click on the Submit & Process Button", accept_multiple_files=True,key = "cluploader")
        if st.button("Submit & Process",key = "CL"):
            with st.spinner("Processing..."):
                raw_text2 = get_ppt_text(ppt_docs)
                # st.write(raw_text2)
                save_docs_to_txt(raw_text2,"Job Text Files/cl_text.txt")
                st.success("Done")

        st.title("Add your Style of English:")
        ppt_docs = st.file_uploader("Upload your PDF Files and Click on the Submit & Process Button", accept_multiple_files=True,key = "englishuploader")
        if st.button("Submit & Process",key = "ENGLISH"):
            with st.spinner("Processing..."):
                raw_text2 = get_ppt_text(ppt_docs)
                # st.write(raw_text2)
                save_docs_to_txt(raw_text2,"Job Text Files/english_style.txt")
                st.success("Done")

        st.title("Add Context related Documents:")
        ppt_docs = st.file_uploader("Upload your PDF Files and Click on the Submit & Process Button", accept_multiple_files=True, key = "contextuploader")
        if st.button("Submit & Process",key = "CONTEXT"):
            with st.spinner("Processing..."):
                raw_text2 = get_ppt_text(ppt_docs)
                # st.write(raw_text2)
                text_chunks = get_text_chunks(raw_text2)
                # st.write(text_chunks)
                get_vector_store(text_chunks)
                st.success("Done")



if __name__ == "__main__":
    main()






