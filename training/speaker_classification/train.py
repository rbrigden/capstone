import os, time, sys
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.nn.utils.rnn import pad_sequence
import training.speaker_verification.model as models
import torch.optim.lr_scheduler
import torch.optim as optim
import numpy as np


class SpeakerClassifierTrainer:

    def __init__(self,
                 batch_size,
                 learning_rate,
                 num_speakers=1000):
        self.model = models.DenseIdentifyAndEmbed(num_speakers).cuda()
        self.batch_size = batch_size
        self.optimizer = optim.Adam(self.model.parameters(),
                                    lr=learning_rate,
                                    weight_decay=5e-4)


    def resume(self, checkpoint_path):
        cpd = torch.load(checkpoint_path, map_location=lambda storage, loc: storage)
        self.model.load_state_dict(cpd["model"])
        self.optimizer.load_state_dict(cpd["optimizer"])

    def checkpoint(self, path):
        cpd = {
            "model": self.model.state_dict(),
            "optimizer": self.optimizer.state_dict(),
        }
        torch.save(cpd, path)

    def _process_data_batch(self, data_batch, mode='zeros'):
        # pad the sequences, each seq must be (L, *)
        seq_lens = [len(x) for x in data_batch]

        if mode == 'zeros':
            seq_batch = pad_sequence(data_batch, batch_first=True)
        elif mode == 'wrap':
            seq_batch = torch.stack([torch.FloatTensor(np.pad(x.numpy(), mode='wrap', axis=0)) for x in data_batch])
        else:
            raise ValueError("Invalid mode specified")
        return seq_batch.unsqueeze(1).cuda(), seq_lens

    def train_epoch(self, data_loader):
        for idx, (data_batch, label_batch) in enumerate(data_loader):
            seq_batch, seq_lens = self._process_data_batch(data_batch)
            self.optimizer.zero_grad()
            preds, _ = self.model([seq_batch, seq_lens])
            loss = F.nll_loss(preds, label_batch.cuda())
            loss.backward()
            self.optimizer.step()
            print("here2")

            correct = (torch.argmax(preds, dim=1) == label_batch.cuda()).sum()
            yield loss.item(), correct.item()

    def validation(self, data_loader):
        self.model.eval()
        num_correct = 0
        for idx, (data_batch, label_batch) in enumerate(data_loader):
            seq_batch, seq_lens = self._process_data_batch(data_batch, mode='wrap')
            preds, _ = self.model([seq_batch, seq_lens])
            correct = (torch.argmax(preds, dim=1) == label_batch.cuda()).sum()
            num_correct += correct.item()
        self.model.train()
        return 1.0 - (num_correct / float(len(data_loader.dataset)))

    def compute_verification_eer(self, validator):
        self.model.eval() 
        eer = validator.evaluate(self.model)
        self.model.train()
        return eer

            
            

