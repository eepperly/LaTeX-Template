%%
%% This is file `ucsdletter.cls'
%% It is based on the LaTeX2e letter.cls, but with changes to print a specified letterhead.
%% It gathers personal information from a configuration file, without which it cannot function.
%% Initial version by Michael Sharpe (msharpe@ucsd.edu), January 15, 2007
\NeedsTeXFormat{LaTeX2e}[1996/06/01]
\ProvidesClass{ucsdletter}
              [2007/1/15
               Based on standard LaTeX letter class]
\newcommand\@ptsize{}
\newcommand\cfgfilename{mylettercfg.tex}% the default
\DeclareOption{a4paper}
   {\setlength\paperheight {297mm}%
    \setlength\paperwidth  {210mm}}
\DeclareOption{a5paper}
   {\setlength\paperheight {210mm}%
    \setlength\paperwidth  {148mm}}
\DeclareOption{b5paper}
   {\setlength\paperheight {250mm}%
    \setlength\paperwidth  {176mm}}
\DeclareOption{letterpaper}
   {\setlength\paperheight {11in}%
    \setlength\paperwidth  {8.5in}}
\DeclareOption{legalpaper}
   {\setlength\paperheight {14in}%
    \setlength\paperwidth  {8.5in}}
\DeclareOption{executivepaper}
   {\setlength\paperheight {10.5in}%
    \setlength\paperwidth  {7.25in}}
\DeclareOption{landscape}
   {\setlength\@tempdima   {\paperheight}%
    \setlength\paperheight {\paperwidth}%
    \setlength\paperwidth  {\@tempdima}}
\DeclareOption{10pt}{\renewcommand\@ptsize{0}}
\DeclareOption{11pt}{\renewcommand\@ptsize{1}}
\DeclareOption{12pt}{\renewcommand\@ptsize{2}}
%
% Add ability to parse for a config file
\if@compatibility
  \DeclareOption{twoside}{\@latexerr{No `twoside' layout for letters}%
                                   \@eha}
\else
  \DeclareOption{twoside}{\@twosidetrue  \@mparswitchtrue}
\fi
\DeclareOption{oneside}{\@twosidefalse \@mparswitchfalse}
\DeclareOption{draft}{\setlength\overfullrule{5pt}}
\DeclareOption{final}{\setlength\overfullrule{0pt}}
\DeclareOption{leqno}{\input{leqno.clo}}
\DeclareOption{fleqn}{\input{fleqn.clo}}
\DeclareOption*{\let\tmp\CurrentOption\IfFileExists{\tmp}%
{\renewcommand\cfgfilename{\tmp}}%
{\PackageWarning{Config}{File not found: \tmp}}%
}
%\DeclareOption*{\renewcommand\cfgfilename{\CurrentOption}}
\ExecuteOptions{letterpaper,10pt,oneside,onecolumn,final}
\ProcessOptions\relax
\RequirePackage{graphicx}
%
%default graphic file name for seal
\def\sealfile{ucseal}% ucseal.eps and ucseal.pdf should be available
%increase tolerance
\newif\ifsigfile \sigfilefalse
\def\sigfilename{}
\newlength\sigheight
\setlength\sigheight{.5in}
\newcommand\usesig[2]{\setlength\sigheight{#1}\def\sigfilename{#2}\sigfiletrue}
\tolerance=1600
\hbadness=10000
\input{size1\@ptsize.clo}
% this sets the textwidth and textheight, in particular.
% Code for debugging boxes (files at CTAN, see TeX in Practice by Stephan von Bechtolsheim)
%\input inputd.tip
%\InputD{box-mac.tip}
%\catcode`\@ = 11
% end of debug code for boxes
\setlength\lineskip{1\p@}
\setlength\normallineskip{1\p@}
\renewcommand\baselinestretch{}
\setlength\parskip{0.7em}
\setlength\parindent{0\p@}
\@lowpenalty   51
\@medpenalty  151
\@highpenalty 301
\setlength\headheight{12\p@}
\setlength\headsep   {45\p@}
\setlength\footskip{25\p@}
%new dimensions required for subhead
\newdimen\subheadlefti
\newdimen\subheadrighti
\newdimen\subheadcolBCsep
\subheadlefti=0pt
\subheadrighti=0pt
\subheadcolBCsep=0in
\newdimen\logotop % distance from top of paper to logo top--may be redefined
\setlength\logotop{.53in}
\newdimen\subheadtopsep
\setlength\subheadtopsep{.125in}
\newdimen\subheadbaselineskip
\setlength\subheadbaselineskip{10pt}
\def\subheadfontname{ptmr at 8pt}% may be redefined in mylettercfg.tex
\font\subheadfont=\subheadfontname
\setlength\textwidth{6in}
\newif\ifsubheadinhead \subheadinheadtrue
\newif\ifvcentering \vcenteringtrue
\newif\ifcustomsubhead \customsubheadfalse
\newcommand*{\signature}[1]{\def\fromsig{#1}}
%
\newbox\c@lA
\newbox\c@lB
\newbox\c@lC
\newcommand{\colm}[3][l]{%\create a subhead column, eg: \colm[r]{A}{lines of text}
\baselineskip=\subheadbaselineskip\subheadfont
\def\itm##1{\hbox{\sfcode`.=1000 ##1}}
\setbox0=\vtop{#3}
\def\letr{r}\def\frstarg{#1}
\ifx\frstarg\letr% want right aligned text in this colm
\@tempdima=\wd0
\def\itm##1{\hbox to \@tempdima{\sfcode`.=1000\hfil##1}}
\setbox0=\vtop{#3}
\fi
\def\@@temp{c@l#2}\global\expandafter\setbox\csname \@@temp\endcsname=\box0}
%
%input our own data selections and configuration---must be here to get correct centering
\InputIfFileExists{\cfgfilename}{}{\PackageWarning{Config}{File `\cfgfilename' not found}\input mylettercfg.tex}
\if@compatibility
  \setlength\textwidth{365\p@}
  \setlength\textheight{505\p@}
\fi
%\textwidth must be set by this point in order for other related settings to be correct
\if@compatibility
  \setlength\oddsidemargin{53pt}
  \setlength\evensidemargin{53pt}
  \setlength\marginparwidth{90pt}
\else
  \setlength\@tempdima{\paperwidth}
  \addtolength\@tempdima{-2in}
  \addtolength\@tempdima{-\textwidth}
  \setlength\oddsidemargin   {.5\@tempdima}
  \setlength\evensidemargin  {\oddsidemargin}
  \setlength\marginparwidth  {90\p@}
\fi
\setlength\marginparsep {11\p@}
\setlength\marginparpush{5\p@}
\setlength\topmargin{27pt}
\setlength\footnotesep{12\p@}
\setlength{\skip\footins}{10\p@ \@plus 2\p@ \@minus 4\p@}
% added to compute header box and sizes for firstpage
\newbox\@sealbox
\newbox\@subheadbox
\newdimen\headerwidth
\newdimen\headervoffset
\newdimen\headboxheight
\newdimen\headboxdepth
\setlength\headervoffset{1in}%
\advance\headervoffset -\logotop%
\advance\headervoffset by \topmargin%
\advance\headervoffset by \headheight%
\setbox5=\hbox{\includegraphics{\sealfile}}%
\setlength\headerwidth{\wd5}%
% Process subhead
\@tempdima=\ifsubheadinhead\headerwidth\else\textwidth\fi
\ifcustomsubhead%
  \setbox\@subheadbox=\hbox to \@tempdima{\sfcode`.=1000\mysubhead}
\else
 % \baselineskip=\subheadbaselineskip%
\setbox\@subheadbox=\hbox to \@tempdima{\hbox to \subheadlefti{\hfil}%
\box\c@lA\hfil \box\c@lB%
\hbox to \subheadcolBCsep{\hfil}\box\c@lC\hbox to \subheadrighti{\hfil}}%
\baselineskip\z@skip \lineskip\z@skip \lineskiplimit\z@%
\fi%\ifcustomsubhead
\setbox0=\vbox{%
\box5
\ifsubheadinhead% add subhead below letterhead
\vspace*{\subheadtopsep}%
\box\@subheadbox%
\fi
}% 
\headboxdepth=\ht0
\advance\headboxdepth by \dp0
\advance\headboxdepth by -\headervoffset% this much will overlap below the head
\setbox1=\vbox to \headervoffset{\box0}% move ref point
\setbox\@sealbox=\vbox to \headheight{\vss\box1}
%end of \@sealbox construction
% Now check whether sealbox so big vertically as to require 
% the first page to start lower.
\advance\headboxdepth -\headsep% amount it protrudes into text area
\ifdim\headboxdepth<\z@\headboxdepth=\z@\fi
% end of code for \@sealbox---see also \ps@firstpage and \opening
\if@twoside
  \def\ps@headings{%
      \let\@oddfoot\@empty\let\@evenfoot\@empty
      \def\@oddhead{\slshape\headtoname{} \ignorespaces\toname
                    \hfil \@date
                    \hfil \pagename{} \thepage}%
      \let\@evenhead\@oddhead}
\else
  \def\ps@headings{%
      \let\@oddfoot\@empty
      \def\@oddhead{\slshape\headtoname{} \ignorespaces\toname
                    \hfil \@date
                    \hfil \pagename{} \thepage}}
\fi
\def\ps@empty{%
      \let\@oddfoot\@empty\let\@oddhead\@empty
      \let\@evenfoot\@empty\let\@evenhead\@empty}
%
\def\ps@firstpage{%
       \def\@oddhead{% have to be very careful not to introduce any spaces
\hss\copy\@sealbox %use\copy instead of \box in case more than one letter
\hss
}% end of \@oddhead
\let\@oddfoot\@empty
}
%\def\@oddfoot{\raisebox{-45\p@}[\z@]{%
%        \hb@xt@\textwidth{\hspace*{100\p@}%
%          \ifcase \@ptsize\relax
%             \normalsize
%          \or
%             \small
%          \or
%             \footnotesize
%          \fi
%        \fromlocation \hfill \telephonenum}}\hss}}
\def\ps@plain{%
      \let\@oddhead\@empty
      \def\@oddfoot{\normalfont\hfil\thepage\hfil}%
      \def\@evenfoot{\normalfont\hfil\thepage\hfil}}
%\newcommand*{\name}[1]{\def\fromname{#1}}
%\newcommand*{\address}[1]{\def\fromaddress{#1}}
%\newcommand*{\location}[1]{\def\fromlocation{#1}}
%\newcommand*{\telephone}[1]{\def\telephonenum{#1}}
%\name{}
%\signature{}
%\address{}
%\location{}
%\telephone{}
\newcommand*{\makelabels}{%
  \AtBeginDocument{%
     \let\@startlabels\startlabels
     \let\@mlabel\mlabel
     \if@filesw
       \immediate\write\@mainaux{\string\@startlabels}\fi}%
  \AtEndDocument{%
     \if@filesw\immediate\write\@mainaux{\string\clearpage}\fi}}
\@onlypreamble\makelabels
\newenvironment{letter}[1]
  {\newpage
    \if@twoside \ifodd\c@page
                \else\thispagestyle{empty}\null\newpage\fi
    \fi
    \c@page \@ne
    \c@footnote \z@
    \interlinepenalty=200 % smaller than the TeXbook value
    \@processto{\leavevmode\ignorespaces #1}}
  {\stopletter\@@par\pagebreak\@@par
    \if@filesw
      \begingroup
        \let\\=\relax
        \let\protect\@unexpandable@protect
        \immediate\write\@auxout{%
          \string\@mlabel{\returnaddress}{\toname\\\toaddress}}%
      \endgroup
    \fi}
\long\def\@processto#1{%
  \@xproc #1\\@@@%
  \ifx\toaddress\@empty
  \else
    \@yproc #1@@@%
  \fi}
\long\def\@xproc #1\\#2@@@{\def\toname{#1}\def\toaddress{#2}}
\long\def\@yproc #1\\#2@@@{\def\toaddress{#2}}
\newcommand*{\stopbreaks}{%
  \interlinepenalty\@M
  \def\par{\@@par\nobreak}%
  \let\\\@nobreakcr
  \let\vspace\@nobreakvspace}
\DeclareRobustCommand\@nobreakvspace
   {\@ifstar\@nobreakvspacex\@nobreakvspacex}
\def\@nobreakvspacex#1{%
  \ifvmode
    \nobreak\vskip #1\relax
  \else
    \@bsphack\vadjust{\nobreak\vskip #1}\@esphack
  \fi}
\def\@nobreakcr{\@ifstar{\@normalcr*}{\@normalcr*}}
\newcommand*{\startbreaks}{%
  \let\\\@normalcr
  \interlinepenalty 200%
  \def\par{\@@par\penalty 200\relax}}
\newdimen\longindentation
\longindentation=.5\textwidth
\newdimen\indentedwidth
\indentedwidth=\textwidth
\advance\indentedwidth -\longindentation
%
% The opening macro here is different from the letter opening macro.
% fromaddress is ignored here---that information is handled elsewhere
\newcommand*{\opening}[1]{%
      \thispagestyle{firstpage}%
    %added skip for possible long header
\null\vskip\headboxdepth
\ifsubheadinhead\else\copy\@subheadbox\vskip25pt\fi
{\raggedleft\@date\par}%
   \vspace{2\parskip}%
  {\raggedright \toname \\ \toaddress \par}%
  \vspace{2\parskip}%
  #1\par\nobreak}
% Change \closing to allow an empty argument and to include a scanned signature
\newcommand{\closing}[1]{\par\nobreak\vspace{\parskip}%
  \stopbreaks
  \noindent
  %\ifx\@empty\fromaddress\else
  %\hspace*{\longindentation}\fi
  \parbox{\indentedwidth}{\raggedright\sfcode`.=1000
       \ignorespaces #1\hfil
       \\[\medskipamount]
       \ifsigfile\includegraphics[height=\sigheight]{\sigfilename}\\
       \else
      \hfil\\[5\medskipamount]\fi%
        \ifx\@empty\fromsig
           %\fromname
       \else \fromsig \fi\strut}%
   \par}
\medskipamount=\parskip
\newcommand*{\cc}[1]{%
  \par\noindent
  \parbox[t]{\textwidth}{%
    \@hangfrom{\normalfont\ccname: }%
    \sfcode`.=1000\ignorespaces #1\strut}\par}
\newcommand*{\encl}[1]{%
  \par\noindent
  \parbox[t]{\textwidth}{%
    \@hangfrom{\normalfont\enclname: }%
    \sfcode`.=1000\ignorespaces #1\strut}\par}
\newcommand*{\ps}{\par\startbreaks}
\newcommand*{\stopletter}{}
\newcommand*{\returnaddress}{}
\newcount\labelcount
\newcommand*{\startlabels}{\labelcount\z@
  \pagestyle{empty}%
  \let\@texttop\relax
  \topmargin -50\p@
  \headsep \z@
  \oddsidemargin -35\p@
  \evensidemargin -35\p@
  \textheight 10in
  \@colht\textheight  \@colroom\textheight \vsize\textheight
  \textwidth 550\p@
  \columnsep 26\p@
  \ifcase \@ptsize\relax
    \normalsize
  \or
    \small
  \or
    \footnotesize
  \fi
  \baselineskip \z@
  \lineskip \z@
  \boxmaxdepth \z@
  \parindent \z@
  \twocolumn\relax}
\let\@startlabels=\relax
\newcommand*{\mlabel}[2]{%
  \parbox[b][2in][c]{262\p@}{\strut\sfcode`.=1000\ignorespaces #2}%
  }
\let\@mlabel=\@gobbletwo
\setlength\leftmargini  {2.5em}
\setlength\leftmarginii  {2.2em}
\setlength\leftmarginiii {1.87em}
\setlength\leftmarginiv  {1.7em}
\setlength\leftmarginv  {1em}
\setlength\leftmarginvi {1em}
\setlength\leftmargin    {\leftmargini}
\setlength  \labelsep  {5\p@}
\setlength  \labelwidth{\leftmargini}
\addtolength\labelwidth{-\labelsep}
\setlength\partopsep{0\p@}
\@beginparpenalty -\@lowpenalty
\@endparpenalty   -\@lowpenalty
\@itempenalty     -\@lowpenalty
\def\@listI{\setlength\leftmargin{\leftmargini}%
            \setlength\parsep {0\p@}%
            \setlength\topsep {.4em}%
            \setlength\itemsep{.4em}}
\let\@listi\@listI
\@listi
\def\@listii {\setlength  \leftmargin{\leftmarginii}%
              \setlength  \labelwidth{\leftmarginii}%
              \addtolength\labelwidth{-\labelsep}}
\def\@listiii{\setlength  \leftmargin{\leftmarginiii}%
              \setlength  \labelwidth{\leftmarginiii}%
              \addtolength\labelwidth{-\labelsep}%
              \setlength  \topsep    {.2em}%
              \setlength  \itemsep   {\topsep}}
\def\@listiv {\setlength  \leftmargin{\leftmarginiv}%
              \setlength  \labelwidth{\leftmarginiv}%
              \addtolength\labelwidth{-\labelsep}}
\def\@listv  {\setlength  \leftmargin{\leftmarginv}%
              \setlength  \labelwidth{\leftmarginv}%
              \addtolength\labelwidth{-\labelsep}}
\def\@listvi {\setlength  \leftmargin{\leftmarginvi}%
              \setlength  \labelwidth{\leftmarginvi}%
              \addtolength\labelwidth{-\labelsep}}
\renewcommand\theenumi{\@arabic\c@enumi}
\renewcommand\theenumii{\@alph\c@enumii}
\renewcommand\theenumiii{\@roman\c@enumiii}
\renewcommand\theenumiv{\@Alph\c@enumiv}
\newcommand\labelenumi{\theenumi.}
\newcommand\labelenumii{(\theenumii)}
\newcommand\labelenumiii{\theenumiii.}
\newcommand\labelenumiv{\theenumiv.}
\renewcommand\p@enumii{\theenumi}
\renewcommand\p@enumiii{\theenumi(\theenumii)}
\renewcommand\p@enumiv{\p@enumiii\theenumiii}
\newcommand\labelitemi{\textbullet}
\newcommand\labelitemii{\normalfont\bfseries \textendash}
\newcommand\labelitemiii{\textasteriskcentered}
\newcommand\labelitemiv{\textperiodcentered}
\newenvironment{description}
               {\list{}{\labelwidth\z@ \itemindent-\leftmargin
                        \let\makelabel\descriptionlabel}}
               {\endlist}
\newcommand*{\descriptionlabel}[1]{\hspace\labelsep
                                \normalfont\bfseries #1}
\newenvironment{verse}
               {\let\\=\@centercr
                \list{}{\setlength\itemsep{\z@}%
                        \setlength\itemindent{-15\p@}%
                        \setlength\listparindent{\itemindent}%
                        \setlength\rightmargin{\leftmargin}%
                        \addtolength\leftmargin{15\p@}}%
                \item[]}
               {\endlist}
\newenvironment{quotation}
               {\list{}{\setlength\listparindent{1.5em}%
                        \setlength\itemindent{\listparindent}%
                        \setlength\rightmargin{\leftmargin}}%
                \item[]}
               {\endlist}
\newenvironment{quote}
               {\list{}{\setlength\rightmargin{\leftmargin}}%
                \item[]}
               {\endlist}
\setlength\arraycolsep{5\p@}
\setlength\tabcolsep{6\p@}
\setlength\arrayrulewidth{.4\p@}
\setlength\doublerulesep{2\p@}
\setlength\tabbingsep{\labelsep}
\skip\@mpfootins = \skip\footins
\setlength\fboxsep{3\p@}
\setlength\fboxrule{.4\p@}
\renewcommand\theequation{\@arabic\c@equation}
\DeclareOldFontCommand{\rm}{\normalfont\rmfamily}{\mathrm}
\DeclareOldFontCommand{\sf}{\normalfont\sffamily}{\mathsf}
\DeclareOldFontCommand{\tt}{\normalfont\ttfamily}{\mathtt}
\DeclareOldFontCommand{\bf}{\normalfont\bfseries}{\mathbf}
\DeclareOldFontCommand{\it}{\normalfont\itshape}{\mathit}
\DeclareOldFontCommand{\sl}{\normalfont\slshape}{\relax}
\DeclareOldFontCommand{\sc}{\normalfont\scshape}{\relax}
\DeclareRobustCommand*{\cal}{\@fontswitch{\relax}{\mathcal}}
\DeclareRobustCommand*{\mit}{\@fontswitch{\relax}{\mathnormal}}
\renewcommand\footnoterule{%
  \kern-\p@
  \hrule \@width .4\columnwidth
  \kern .6\p@}
\long\def\@makefntext#1{%
    \noindent
    \hangindent 5\p@
    \hb@xt@5\p@{\hss\@makefnmark}#1}
%% added 20060127 by msharpe: code for multiletter
\newcommand\multiletter[3][*]{%
	\newcount\salutpref \salutpref=0 % 0=empty, 1=aster, 2=predefined
	\newcount\addrlines %number of address lines read this iteration
	\newcount\linetype % 0=\par, 1=normal address line, 2=salutation,3=EOF, 4=ignore
	\def\per{.}
	\newtoks\dbs \dbs={\\}
	\newread\mys
	\def\ltr{\begin{letter}{\addrline}\opening{\salutation}\letterbody\closing{\closingdef}\end{letter}}
	\def\aster{*}
	\def\readaddrs{% read all addresses and make letters for each
		\loop
			\addrlines=0	
			\linetype=0
			\xdef\ttoname{}
			\let\savepar\par %save current meaning of \par
			\let\par\@@par %the original , defined in latex
			\def\mypar{\par} % for use in \ifx
			\readloop 
			\let\par\savepar %restore to previous value
			\ifnum\addrlines>0
				\wlog{\string\readaddrs: addrlines=\the\addrlines}
				\ifnum\linetype=2 %there was a dotted line at end of addr
				\else %no dotted entry
					\ifnum\salutpref=1 \def\salutation{Dear \ttoname}\fi
					\ifnum\salutpref=2 \let\salutation\salutationdef \fi
				\fi
				\ltr %emit a letter
			\fi 
			\ifnum\linetype<3 %continue unless EOF
		\repeat	
	}
	\def\readloop{% read a single address/salutation
		\ifeof\mys
			\closein\mys
			\linetype=3
			\let\next=\relax
		\else
			\read\mys to \LineRead
			\wlog{\string\readloop:  Read Line: "\LineRead."}
			\ifx\LineRead\empty %starts with %
				\linetype=4 %ignore
			\else
				\ifx\LineRead\mypar\linetype=0\else\checksalute\LineRead\fi
				\wlog{\string\readloop: linetype=\the\linetype}
				%else check if it begins with .
			\fi
			\ifnum\linetype=1	%just read a normal address line
				\ifnum\addrlines=0 %start new address
					\xdef\ttoname{\LineRead}
					\xdef\addrline{\LineRead}
				\else % add to current address
					\toks0=\expandafter{\addrline} %expand one level
					\xdef\addrline{\the\toks0 \the\dbs \LineRead} %avoid expanding \\
				\fi
				\advance\addrlines by 1
				\let\next=\readloop
			\else
				\ifnum\linetype<4
					\let\next=\relax
				\else
					\let\next=\readloop %ignored line
				\fi
			\fi
		\fi
		\next
		
	} %\end \readloop
	\def\onetwo##1##2[[[{%
			\def\tmpp{##1}
			\ifx\tmpp\per\linetype=2\xdef\salutation{##2}\fi 
	}
	\def\checksalute##1{%
		\linetype=1 %assume normal until proven otherwise
		\xdef\salutation{}
		\toks0=\expandafter{##1}
		\expandafter\onetwo\the\toks0 [[[
	}
	\xdef\salutationdef{#1}%default salutation to use if none specified
	\ifx\salutationdef\aster \salutpref=1
	\else
		\ifx\salutationdef\empty\else \salutpref=2\fi
	\fi
	\xdef\closingdef{#3}
	\openin\mys = #2
	\ifeof\mys
		\errormessage{Openin failed}
	\else
		\readaddrs
	\fi
} %end \multiletter
%% end added code
\newcommand*{\ccname}{cc}
\newcommand*{\enclname}{encl}
\newcommand*{\pagename}{Page}
\newcommand*{\headtoname}{To}
\newcommand*{\today}{\ifcase\month\or
  January\or February\or March\or April\or May\or June\or
  July\or August\or September\or October\or November\or December\fi
  \space\number\day, \number\year}
\setlength\columnsep{10\p@}
\setlength\columnseprule{0\p@}
\pagestyle{plain}
\pagenumbering{arabic}
\raggedbottom
\ifvcentering
  \def\@texttop{\ifnum\c@page=1\vskip \z@ plus.00006fil\relax\fi}
\else
  \def\@texttop{\ifnum\c@page=1\vskip \z@ \fi}
\fi
\onecolumn
\endinput
%%
%% End of file `ucsdletter.cls'.

% see ucsdlettercls.txt for notes on the Latex output routines and the design choices in this file