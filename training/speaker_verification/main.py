import time
import argparse
import torch
import torch.utils.data as dutils
import training.speaker_verification.train as train
import training.speaker_verification.verify as verify
import data.voxceleb.voxceleb as voxceleb
import data.nist.new.nist as nist
from training.speaker_verification.loading import ContrastiveSampler, Siamese
import tensorboardX


def tboard_plot(writer, step, update_dict):
    for k, v in update_dict.items():
        writer.add_scalar(k, v, step)


def train_verification(args):
    writer = tensorboardX.SummaryWriter()

    start = time.time()

    speakers = list(range(1200))

    if args.dset == 'nist':
        train_set, val_set = nist.NistID.create_split(args.dset_path, split=0.9, shuffle=True)
        train_collate_fn = nist.clip_collate(1000, sample=True)
        val_collate_fn = nist.clip_collate(1000, sample=False)
    else:
        train_set, val_set = voxceleb.VoxcelebID.create_split(args.dset_path, speakers, split=0.9, shuffle=True)
        train_collate_fn = voxceleb.voxceleb_clip_collate(1000, sample=True)
        val_collate_fn = voxceleb.voxceleb_clip_collate(1000, sample=False)

    if args.resume is not None:

        print("Loading classifier params from {}".format(args.resume))
        trainer = train.VerificationTrainer(batch_size=args.batch_size,
                                            learning_rate=args.lr,
                                            num_speakers=len(speakers),
                                            resume=args.resume,
                                            pad=args.pad)
    else:

        if args.dset == 'nist':
            num_speakers = len(train_set.sparse_to_dense_id.values())
            print("num speakers", num_speakers)
        else:
            num_speakers = len(speakers)
        trainer = train.VerificationTrainer(batch_size=args.batch_size,
                                            learning_rate=args.lr,
                                            num_speakers=num_speakers,
                                            pad=args.pad)
        print("Initialize classifier params from scratch")

    siamese_train_set = Siamese(train_set)


    def siamese_collate(batch):
        b1 = train_collate_fn([[u1, l1] for u1, _, l1, _ in batch])
        b2 = train_collate_fn([[u2, l2] for _, u2, _, l2 in batch])
        return b1[0], b2[0], b1[1], b2[1]

    if not args.classification:
        siamese_batch_sampler = ContrastiveSampler(train_set.utterance_labels, len(speakers), args.batch_size)
        loader = dutils.DataLoader(siamese_train_set, batch_sampler=siamese_batch_sampler,
                                                 collate_fn=siamese_collate, num_workers=8)
    else:
        loader = dutils.DataLoader(train_set, batch_size=args.batch_size, shuffle=True,
                                         collate_fn=train_collate_fn, num_workers=8, pin_memory=True)

    val_loader = dutils.DataLoader(val_set, batch_size=5, shuffle=False, collate_fn=val_collate_fn,
                                   num_workers=8, pin_memory=True)

    # Verification EER computation
    veri_evaluator = verify.VerificationEvaluator(args.dset_test_path, pad=args.pad)

    total_samples_processed = 0

    initial_alpha = args.alpha
    best_eer = 1.0
    end = time.time()
    print("Setup done. Took {} secs".format(round(end - start, 4)))
    total_steps = 0
    for e in range(args.epochs):
        total_loss = 0
        nbatches = 0

        # Train for an epoch
        start = time.time()
        num_correct = 0

        if args.classification:
            runner = trainer.train_epoch_classification(loader)
            for loss, correct in runner:
                total_samples_processed += args.batch_size
                nbatches += 1
                total_steps += 1
                num_correct += correct
                tboard_update = {
                    "loss": loss,
                    "train_error": 1 - correct / args.batch_size
                }
                tboard_plot(writer, total_steps, tboard_update)
        else:
            runner = trainer.train_epoch_verification(loader, initial_alpha)
            for vloss, best_margin in runner:
                total_samples_processed += args.batch_size
                nbatches += 1
                total_loss += vloss
                total_steps += 1

                tboard_update = {
                    "verification_loss": vloss,
                    "net_loss": vloss,
                    "current_margin": best_margin
                }
                tboard_plot(writer, total_steps, tboard_update)


                # if (total_steps+1) % args.checkpoint_freq == 0:
                #     veri_eer = trainer.compute_verification_eer(veri_evaluator)
                #     if veri_eer < best_eer:
                #         print("saving checkpoint")
                #         trainer.checkpoint(args.checkpoint_path)
                #         best_eer = veri_eer
                #
                #     tboard_update = {
                #         "eer": veri_eer,
                #     }
                #     tboard_plot(writer, e, tboard_update)


        end = time.time()

        epoch_time = end - start
        val_error = trainer.validation(val_loader)
        veri_eer = trainer.compute_verification_eer(veri_evaluator)

        # Compute validation error
        if veri_eer < best_eer:
            print("saving checkpoint")
            trainer.checkpoint(args.checkpoint_path)
            best_eer = veri_eer

        tboard_update = {
            "eer": veri_eer,
            "validation_error": val_error,
        }

        tboard_plot(writer, e, tboard_update)

        print("Epoch {} of {} took {} seconds \n"
              "\tValidation error: {}\n"
              "\tEER: {}\n".format(e + 1, args.epochs, epoch_time, val_error, veri_eer))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dset-path', type=str, default="/home/rbrigden/voxceleb/processed")
    parser.add_argument('--dset-test-path', type=str, default="/home/rbrigden/voxceleb/test/processed")
    parser.add_argument('--checkpoint-path', type=str, default="models/verification/base.pt")
    parser.add_argument('--classification', action='store_true', default=False)
    parser.add_argument('--resume', type=str, default=None)
    parser.add_argument('--epochs', type=int, default=10)
    parser.add_argument('--batch-size', type=int, default=100)
    parser.add_argument('--device', type=int, default=0)
    parser.add_argument('--pad', type=str, default='zeros')
    parser.add_argument('--dset', type=str, default='nist')

    parser.add_argument('--checkpoint-freq', type=int, default=100)


    parser.add_argument('--alpha', type=float, default=0.5,
                        help="ratio of verification loss to classification loss")

    parser.add_argument('--lr', type=float, default=5e-4)
    args = parser.parse_args()
    with torch.cuda.device(args.device):
        train_verification(args)
