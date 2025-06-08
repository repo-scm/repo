package manifest

import (
	"encoding/xml"
	"fmt"
	"os"
)

type Manifest struct {
	XMLName  xml.Name   `xml:"manifest"`
	Notice   string     `xml:"notice,omitempty"`
	Remote   []Remote   `xml:"remote"`
	Default  Default    `xml:"default"`
	Project  []Project  `xml:"project"`
	RepoHook []RepoHook `xml:"repo-hooks,omitempty"`
}

type Remote struct {
	Name     string `xml:"name,attr"`
	Alias    string `xml:"alias,attr,omitempty"`
	Fetch    string `xml:"fetch,attr"`
	Review   string `xml:"review,attr,omitempty"`
	Revision string `xml:"revision,attr,omitempty"`
}

type Default struct {
	Remote     string `xml:"remote,attr,omitempty"`
	Revision   string `xml:"revision,attr,omitempty"`
	DestBranch string `xml:"dest-branch,attr,omitempty"`
	SyncJ      string `xml:"sync-j,attr,omitempty"`
	SyncC      string `xml:"sync-c,attr,omitempty"`
	SyncS      string `xml:"sync-s,attr,omitempty"`
}

type Project struct {
	Name       string       `xml:"name,attr"`
	Path       string       `xml:"path,attr,omitempty"`
	Remote     string       `xml:"remote,attr,omitempty"`
	Revision   string       `xml:"revision,attr,omitempty"`
	DestBranch string       `xml:"dest-branch,attr,omitempty"`
	Groups     string       `xml:"groups,attr,omitempty"`
	SyncC      string       `xml:"sync-c,attr,omitempty"`
	SyncS      string       `xml:"sync-s,attr,omitempty"`
	SyncTags   string       `xml:"sync-tags,attr,omitempty"`
	Upstream   string       `xml:"upstream,attr,omitempty"`
	CloneDepth string       `xml:"clone-depth,attr,omitempty"`
	ForcePath  string       `xml:"force-path,attr,omitempty"`
	CopyFile   []CopyFile   `xml:"copyfile,omitempty"`
	LinkFile   []LinkFile   `xml:"linkfile,omitempty"`
	Annotation []Annotation `xml:"annotation,omitempty"`
}

type CopyFile struct {
	Src  string `xml:"src,attr"`
	Dest string `xml:"dest,attr"`
}

type LinkFile struct {
	Src  string `xml:"src,attr"`
	Dest string `xml:"dest,attr"`
}

type Annotation struct {
	Name  string `xml:"name,attr"`
	Value string `xml:"value,attr"`
}

type RepoHook struct {
	InProject   string `xml:"in-project,attr"`
	EnabledList string `xml:"enabled-list,attr,omitempty"`
}

func ParseManifest(filePath string) (*Manifest, error) {
	data, err := os.ReadFile(filePath)
	if err != nil {
		return nil, fmt.Errorf("failed to read manifest file: %w", err)
	}

	return ParseManifestFromBytes(data)
}

func ParseManifestFromBytes(data []byte) (*Manifest, error) {
	var manifest Manifest
	err := xml.Unmarshal(data, &manifest)
	if err != nil {
		return nil, fmt.Errorf("failed to parse manifest XML: %w", err)
	}

	return &manifest, nil
}
