#define _GNU_SOURCE
/* VirtualEdge v0.27: offline guest-side VERIFIED FILE STAGING ONLY.
 * Does not write block devices, modify boot state, or reboot.
 * Stage root must be a private root/user-owned 0700 directory.
 */
#include <errno.h>
#include <fcntl.h>
#include <linux/fs.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#include <limits.h>

#define LIMIT_IMAGE (1024ULL*1024ULL*1024ULL)
static void die(const char *msg) { fprintf(stderr,"FAIL: %s (%s)\n",msg,strerror(errno)); exit(1); }
static void cleanup(int rootfd, int tmpfd, const char *name) {
    if (tmpfd >= 0) {
        unlinkat(tmpfd,"manifest.json",0);
        unlinkat(tmpfd,"manifest.sig",0);
        unlinkat(tmpfd,"image.bin",0);
        close(tmpfd);
    }
    if (rootfd >= 0 && name && *name) unlinkat(rootfd,name,AT_REMOVEDIR);
}
static int copy_bounded(int dirfd, const char *src, const char *dest, unsigned long long limit) {
    int fd=open(src,O_RDONLY|O_NOFOLLOW|O_CLOEXEC|O_NONBLOCK);
    if(fd<0) return -1;
    struct stat st;
    if(fstat(fd,&st)<0 || !S_ISREG(st.st_mode) || st.st_size<=0 || (unsigned long long)st.st_size>limit) {
        close(fd); errno=EINVAL; return -1;
    }
    int out=openat(dirfd,dest,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    if(out<0) {close(fd);return -1;}
    unsigned long long total=0;
    char buffer[65536];
    int ok=1;
    for(;;) {
        ssize_t n=read(fd,buffer,sizeof(buffer));
        if(n<0 && errno==EINTR) continue;
        if(n<0) {ok=0;break;}
        if(n==0) break;
        total+=(unsigned long long)n;
        if(total>limit || total>(unsigned long long)st.st_size) {ok=0; errno=EFBIG;break;}
        for(ssize_t at=0;at<n;) {
            ssize_t w=write(out,buffer+at,(size_t)(n-at));
            if(w<0 && errno==EINTR) continue;
            if(w<=0){ok=0;break;}
            at+=w;
        }
        if(!ok) break;
    }
    if(total!=(unsigned long long)st.st_size) {ok=0;errno=EINVAL;}
    if(ok && fsync(out)<0) ok=0;
    if(close(out)<0) ok=0;
    close(fd);
    if(!ok) return -1;
    return 0;
}
static int run_verify(const char *binary, const char *dir, const char *pub, const char *board, const char *floor) {
    char mf[PATH_MAX], sf[PATH_MAX], img[PATH_MAX];
    if(snprintf(mf,sizeof(mf),"%s/manifest.json",dir)>=(int)sizeof(mf) ||
       snprintf(sf,sizeof(sf),"%s/manifest.sig",dir)>=(int)sizeof(sf) ||
       snprintf(img,sizeof(img),"%s/image.bin",dir)>=(int)sizeof(img)) return -1;
    pid_t pid=fork(); if(pid<0)return -1;
    if(pid==0) {
        char *const argv[]={(char*)binary,mf,sf,img,(char*)pub,(char*)board,(char*)floor,NULL};
        execv(binary,argv);
        _exit(127);
    }
    int status;
    while(waitpid(pid,&status,0)<0){if(errno==EINTR)continue;return -1;}
    return WIFEXITED(status) && WEXITSTATUS(status)==0 ? 0 : -1;
}
int main(int argc, char **argv) {
    if(argc!=9) {
        fprintf(stderr,"Usage: %s PRIVATE_STAGE_DIR MANIFEST SIG IMAGE TRUSTED_PUB BOARD MIN_VERSION TRUSTED_VERIFIER_BIN\n",argv[0]);
        return 2;
    }
    const char *root=argv[1];
    if(root[0]!='/') {fprintf(stderr,"FAIL: staging directory must be absolute\n");return 1;}
    if(argv[8][0]!='/') {fprintf(stderr,"FAIL: verifier executable must be absolute\n");return 1;}
    int rootfd=open(root,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(rootfd<0) die("open private staging directory");
    struct stat st;
    if(fstat(rootfd,&st)<0 || !S_ISDIR(st.st_mode) || st.st_uid!=geteuid() || (st.st_mode&0777)!=0700) {
        fprintf(stderr,"FAIL: staging directory must be owned by current user and mode 0700\n");
        close(rootfd);return 1;
    }
    struct stat exists;
    if(fstatat(rootfd,"candidate",&exists,AT_SYMLINK_NOFOLLOW)==0 || errno!=ENOENT) {
        fprintf(stderr,"FAIL: candidate already exists; refusing overwrite\n");close(rootfd);return 1;
    }
    char tmp[PATH_MAX];
    if(snprintf(tmp,sizeof(tmp),"%s/.stage-XXXXXX",root)>=(int)sizeof(tmp)) {close(rootfd);return 1;}
    if(!mkdtemp(tmp))die("create private staging directory");
    const char *name=strrchr(tmp,'/');name=name?name+1:tmp;
    int tmpfd=openat(rootfd,name,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(tmpfd<0){cleanup(rootfd,-1,name);close(rootfd);die("open temporary staging directory");}
    int ok=copy_bounded(tmpfd,argv[2],"manifest.json",4096)==0 &&
           copy_bounded(tmpfd,argv[3],"manifest.sig",128)==0 &&
           copy_bounded(tmpfd,argv[4],"image.bin",LIMIT_IMAGE)==0 &&
           fsync(tmpfd)==0 && run_verify(argv[8],tmp,argv[5],argv[6],argv[7])==0;
    if(!ok) {
        fprintf(stderr,"FAIL: copy/verification failed, candidate NOT published\n");
        cleanup(rootfd,tmpfd,name);close(rootfd);return 1;
    }
    if(syscall(SYS_renameat2,rootfd,name,rootfd,"candidate",RENAME_NOREPLACE)<0) {
        fprintf(stderr,"FAIL: atomic publication failed, candidate NOT published\n");
        cleanup(rootfd,tmpfd,name);close(rootfd);return 1;
    }
    if(fsync(rootfd)<0) {
        fprintf(stderr,"WARNING: candidate published but directory durability not confirmed\n");
        close(tmpfd);close(rootfd);return 1;
    }
    close(tmpfd);close(rootfd);
    puts("PASS: signed image staged atomically as candidate/; NO block-device writes or boot selection performed");
    return 0;
}
