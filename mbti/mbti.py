import pandas as pd
import torch
import numpy as np
from torch.utils.data import DataLoader
from transformers import BertTokenizer
from sklearn.model_selection import train_test_split
from torch import cuda
from MBTIDataset import MBTIDataset
from MBTIClassifier import MBTIClassifier
from tqdm import tqdm
device = 'cuda' if cuda.is_available() else 'cpu'

# really imbalanced dataset
# type    posts
# ENFJ    190
# ENFP    675
# ENTJ    231
# ENTP    685
# ESFJ     42
# ESFP     48
# ESTJ     39
# ESTP     89
# INFJ   1470
# INFP   1832
# INTJ   1091
# INTP   1304
# ISFJ    166
# ISFP    271
# ISTJ    205
# ISTP    337

# hyper parameters
TRAIN_BATCH_SIZE = 4
VALID_BATCH_SIZE = 2
EPOCHS = 5
LEARNING_RATE = 1e-05
WEIGHT_DECAY = 1e-05
weights = [
    1/1470,
    1/685,
    1/1304,
    1/1091,
    1/231,
    1/190,
    1/1832,
    1/675,
    1/271,
    1/337,
    1/166,
    1/205,
    1/89,
    1/48,
    1/39,
    1/42
]

def reverse_softmax(vec):
  exponential = np.exp(vec)
  probabilities = exponential / np.sum(exponential)
  return probabilities

def calculate_accuracy(big_idx, targets):
    n_correct = (big_idx == targets).sum().item()
    return n_correct


def compute_metrics(eval_pred):
    logits, labels = eval_pred
    predictions = np.argmax(logits, axis=-1)
    return calculate_accuracy(predictions, labels)


def train(classifier, training_loader, loss_function, optimizer, epoch):
    tr_loss = 0
    n_correct = 0
    nb_tr_steps = 0
    nb_tr_examples = 0
    classifier.train()
    with tqdm(total=len(training)/TRAIN_BATCH_SIZE, miniters=1) as pbar:
        for _, data in enumerate(training_loader, 0):
            ids = data['input_ids'].to(device, dtype=torch.long)
            mask = data['attention_mask'].to(device, dtype=torch.long)
            targets = data['label'].to(device, dtype=torch.long)

            outputs = classifier(ids, mask)
            loss = loss_function(outputs, targets)
            tr_loss = tr_loss + loss.item()
            big_val, big_idx = torch.max(outputs.data, dim=1)
            n_correct += calculate_accuracy(big_idx, targets)

            nb_tr_steps += 1
            nb_tr_examples += targets.size(0)

            optimizer.zero_grad()
            loss.backward()
            # # When using GPU
            optimizer.step()
            pbar.update(1)

    epoch_loss = tr_loss/nb_tr_steps
    epoch_accuracy = (n_correct*100)/nb_tr_examples
    print(f"Training Loss Epoch: {epoch_loss}")
    print(f"Training Accuracy Epoch: {epoch_accuracy}")
    return classifier


def eval(model, testing_loader, loss_function):
    model.eval()
    tr_loss = 0
    n_correct = 0
    n_correct = 0
    nb_tr_steps = 0
    nb_tr_examples = 0
    correct_by_class = {}
    count_by_class = {}
    for i in range(16):
        correct_by_class[str(i)] = 0
        count_by_class[str(i)] = 0
    with torch.no_grad():
        for _, data in enumerate(testing_loader, 0):
            ids = data['input_ids'].to(device, dtype=torch.long)
            mask = data['attention_mask'].to(device, dtype=torch.long)
            targets = data['label'].to(device, dtype=torch.long)
            outputs = model(ids, mask)
            loss = loss_function(outputs, targets)
            tr_loss += loss.item()
            big_val, big_idx = torch.max(outputs.data, dim=1)
            res = calculate_accuracy(big_idx, targets)
            n_correct += res
            indlist = big_idx.tolist()
            tgtlist = targets.tolist()
            for i in range(len(indlist)):
                correct_by_class[str(indlist[i])
                                 ] += 1 if indlist[i] == tgtlist[i] else 0
                count_by_class[str(indlist[i])] += 1
            nb_tr_steps += 1
            nb_tr_examples += targets.size(0)

    epoch_loss = tr_loss/nb_tr_steps
    epoch_accuracy = (n_correct*100)/nb_tr_examples
    print(f"Validation Loss Epoch: {epoch_loss}")
    print(f"Validation Accuracy Epoch: {epoch_accuracy}")

    return (correct_by_class, count_by_class, epoch_accuracy)


# load data
data = pd.read_csv('data/preprocessed/mbti.csv', index_col=None)
training, testing = train_test_split(data, test_size=0.2)
training = training.reset_index()
testing = testing.reset_index()

# tokenize data
BERT_MODEL_NAME = 'bert-base-uncased'
train_params = {'batch_size': TRAIN_BATCH_SIZE,
                'shuffle': True,
                'num_workers': 1
                }
test_params = {'batch_size': VALID_BATCH_SIZE,
               'shuffle': True,
               'num_workers': 1
               }
bert_tokenizer = BertTokenizer.from_pretrained(BERT_MODEL_NAME)
bert_training = MBTIDataset(training, bert_tokenizer, 512)
bert_testing = MBTIDataset(testing, bert_tokenizer, 512)

# load data to DataLoader
bert_training_loader = DataLoader(bert_training, **train_params)
bert_testing_loader = DataLoader(bert_testing, **test_params)

# model declaration
classifier = MBTIClassifier(BERT_MODEL_NAME)
classifier.to(device)
loss_function = torch.nn.CrossEntropyLoss(weight=torch.Tensor(reverse_softmax(weights)).cuda())
optimizer = torch.optim.NAdam(
    params=classifier.parameters(), lr=LEARNING_RATE, weight_decay=WEIGHT_DECAY)
# training based on pre-trained
for epoch in range(EPOCHS):
    print(f'Epoch {epoch}: ')
    classifier = train(classifier, bert_training_loader,
                       loss_function, optimizer, epoch)
    _, _, accuracy = eval(classifier, bert_testing_loader, loss_function)
    print("Accuracy on test data = %0.2f%%" % accuracy)

# testing with finetuned model
# classifier = torch.load('./models/mbti_bert.bin')
# classifier.to(device)

label_to_type = {
    '0': 'INFJ',
    '1': 'ENTP',
    '2': 'INTP',
    '3': 'INTJ',
    '4': 'ENTJ',
    '5': 'ENFJ',
    '6': 'INFP',
    '7': 'ENFP',
    '8': 'ISFP',
    '9': 'ISTP',
    '10': 'ISFJ',
    '11': 'ISTJ',
    '12': 'ESTP',
    '13': 'ESFP',
    '14': 'ESTJ',
    '15': 'ESFJ'
}
correct_by_class, count_by_class, epoch_accuracy = eval(
    classifier, bert_testing_loader, loss_function)
print("Accuracy on test data = %0.2f%%" % epoch_accuracy)
for x in range(16):
    ind = str(x)
    if count_by_class[ind] == 0:
        count_by_class[ind] = 1
    print(
        f'{label_to_type[ind]}: acc = {round(correct_by_class[ind]/count_by_class[ind], 2)}')

# save model and vocab
output_model_file = './models/mbti_weighted_bert.bin'
output_vocab_file = './models/mbti_weighted_bert_vocab.bin'
torch.save(classifier, output_model_file)
bert_tokenizer.save_vocabulary(output_vocab_file)
