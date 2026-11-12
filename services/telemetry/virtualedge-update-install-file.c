#define _GNU_SOURCE
/* VirtualEdge v0.28: verified installation to a NEW REGULAR FILE ONLY.
 * Deliberately does not access block devices, change boot state or reboot.
 */
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <linux/fs.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#define LIMIT_IMAGE (1024ULL*1024ULL*1024ULL)
static int regular_private_dir(const char *path) {
    int fd=open(path,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(fd<0) return -1;
    struct stat st;
    if(fstat(fd,&st)<0 || !S_ISDIR(st.st_mode) || st.st_uid!=geteuid() || (st.st_mode&0777)!=0700){close(fd);errno=EACCES;return -1;}
    return fd;
}
static int copy_file(int srcdir,const char *name,int dst,const char *to,unsigned long long cap){
    int in=openat(srcdir,name,O_RDONLY|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC);
    if(in<0)return -1;
    struct stat st;
    if(fstat(in,&st)<0 || !S_ISREG(st.st_mode) || st.st_size<=0 || (unsigned long long)st.st_size>cap){close(in);errno=EINVAL;return -1;}
    int out=openat(dst,to,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    if(out<0){close(in);return -1;}
    char buf[65536];unsigned long long total=0;int ok=1;
    for(;;){
        ssize_t n=read(in,buf,sizeof(buf));
        if(n<0 && errno==EINTR)continue;
        if(n<0){ok=0;break;}
        if(n==0)break;
        total+=(unsigned long long)n;
        if(total>cap || total>(unsigned long long)st.st_size){ok=0;errno=EFBIG;break;}
        for(ssize_t pos=0;pos<n;){
            ssize_t w=write(out,buf+pos,(size_t)(n-pos));
            if(w<0 && errno==EINTR)continue;
            if(w<=0){ok=0;break;}
            pos+=w;
        }
        if(!ok)break;
    }
    if(total!=(unsigned long long)st.st_size){ok=0;errno=EINVAL;}
    if(ok && fsync(out)<0)ok=0;
    if(close(out)<0)ok=0;
    close(in);
    return ok?0:-1;
}
static int verify(const char *exe,const char *dir,const char *key,const char *board,const char *floor){
    char mf[PATH_MAX],sig[PATH_MAX],img[PATH_MAX];
    if(snprintf(mf,sizeof(mf),"%s/manifest.json",dir)>=(int)sizeof(mf) ||
       snprintf(sig,sizeof(sig),"%s/manifest.sig",dir)>=(int)sizeof(sig) ||
       snprintf(img,sizeof(img),"%s/image.bin",dir)>=(int)sizeof(img))return -1;
    pid_t p=fork();if(p<0)return -1;
    if(p==0){char *const args[]={(char*)exe,mf,sig,img,(char*)key,(char*)board,(char*)floor,NULL};execv(exe,args);_exit(127);}
    int status;while(waitpid(p,&status,0)<0){if(errno==EINTR)continue;return -1;}
    return WIFEXITED(status)&&WEXITSTATUS(status)==0?0:-1;
}
int main(int argc,char **argv){
    if(argc!=7){fprintf(stderr,"Usage: %s PRIVATE_STAGING_DIR PRIVATE_SLOT_DIR TRUSTED_PUB BOARD MIN_VERSION TRUSTED_VERIFIER_BIN\n",argv[0]);return 2;}
    const char *stage=argv[1],*slot=argv[2],*key=argv[3],*board=argv[4],*floor=argv[5],*exe=argv[6];
    if(stage[0]!='/' || slot[0]!='/' || key[0]!='/' || exe[0]!='/'){fprintf(stderr,"FAIL: absolute paths required\n");return 1;}
    int sroot=regular_private_dir(stage), droot=regular_private_dir(slot);
    if(sroot<0 || droot<0){fprintf(stderr,"FAIL: stage and slot roots must be private real directories (0700)\n");if(sroot>=0)close(sroot);if(droot>=0)close(droot);return 1;}
    int candidate=openat(sroot,"candidate",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    struct stat st;
    if(candidate<0 || fstat(candidate,&st)<0 || !S_ISDIR(st.st_mode) || st.st_uid!=geteuid() || (st.st_mode&0777)!=0700){fprintf(stderr,"FAIL: invalid candidate directory\n");goto fail;}
    if(fstatat(droot,"inactive-slot.img",&st,AT_SYMLINK_NOFOLLOW)==0 || errno!=ENOENT){fprintf(stderr,"FAIL: inactive-slot.img already exists; no overwrite permitted\n");goto fail;}
    char tmp[PATH_MAX];
    if(snprintf(tmp,sizeof(tmp),"%s/.install-XXXXXX",slot)>=(int)sizeof(tmp))goto fail;
    if(!mkdtemp(tmp))goto fail;
    const char *name=strrchr(tmp,'/');name=name?name+1:tmp;
    int tmpfd=openat(droot,name,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(tmpfd<0)goto failtmp;
    int ok=copy_file(candidate,"manifest.json",tmpfd,"manifest.json",4096)==0 &&
           copy_file(candidate,"manifest.sig",tmpfd,"manifest.sig",128)==0 &&
           copy_file(candidate,"image.bin",tmpfd,"image.bin",LIMIT_IMAGE)==0 &&
           fsync(tmpfd)==0 && verify(exe,tmp,key,board,floor)==0;
    if(ok){
        if(syscall(SYS_renameat2,tmpfd,"image.bin",droot,"inactive-slot.img",RENAME_NOREPLACE)<0)ok=0;
        else if(fsync(droot)<0){fprintf(stderr,"WARNING: slot published but directory durability uncertain\n");ok=0;}
    }
    unlinkat(tmpfd,"manifest.json",0);unlinkat(tmpfd,"manifest.sig",0);unlinkat(tmpfd,"image.bin",0);
    close(tmpfd);
    if(unlinkat(droot,name,AT_REMOVEDIR)<0){fprintf(stderr,"WARNING: temporary staging cleanup incomplete\n");ok=0;}
    close(candidate);close(sroot);close(droot);
    if(!ok){fprintf(stderr,"FAIL: signed candidate installation rejected; inspect inactive-slot.img before retry\n");return 1;}
    puts("PASS: signed image verified from private snapshot and installed as a NEW REGULAR FILE; no block devices or boot metadata touched");return 0;
failtmp:
    unlinkat(droot,name,AT_REMOVEDIR);
fail:
    if(candidate>=0)close(candidate);
    close(sroot);close(droot);return 1;
}
